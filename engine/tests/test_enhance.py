"""眼牙局部增强（ops/enhance.py）的算子层用例（LNX-PORTRAIT-009 的第一臂）。

这一份只管两件事，而且都按**一手读数**写判据：

① 三条构造性质是不是真的（色相零改动 / 过曝护栏 / 掩膜不越界）——这些是
   冻结件 then 的原话，写成断言而不是写成注释；
② 环下标的几何含义在**真 MediaPipe** 上是不是名字说的那样（延续 test_deform 里
   `test_mouth_landmark_indices_mean_what_the_names_say` 的那条纪律：下标语义不许照抄记忆，
   错了要能响）。

夹具是 `packaging/make-test-portrait.py` 程序化生成的三张变体（露齿 / 眼镜+露齿 / 深肤色露齿），
牙齿与口腔的位置是**画上去的**——所以"掩膜落在牙上而没落到唇面"这类判据有接地的真相可比，
不必靠人眼审图。低光那一臂不另出图：它就是露齿图乘 0.45（写成图只会多一份要审计的哈希）。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from lumaretouch_engine.ops import enhance as ENH
from lumaretouch_engine.ops.grade import rgb_to_hsv_np

REPO = Path(__file__).resolve().parents[2]
FIX_BASE = str(REPO / "engine" / "tests" / "fixtures" / "portrait-1024x1280.jpg")
FIX_SMILE = str(REPO / "engine" / "tests" / "fixtures" / "portrait-smile-1024x1280.jpg")
FIX_GLASS = str(REPO / "engine" / "tests" / "fixtures" / "portrait-glasses-smile-1024x1280.jpg")
FIX_DEEP = str(REPO / "engine" / "tests" / "fixtures" / "portrait-deep-skin-smile-1024x1280.jpg")

# 画上去的解剖位置只用来护住“横梁那几行真的是中性”这种接地前提；牙带行号不在这里
# 写死——test_teeth_mask_… 从像素里读，因为生成器的坐标一跳，写死的行号就会指着一个
# 对的东西报错（上一版就是把画牙缝那两条 line 的 750/804 当成了牙带）。
GLASS_BAR_ROWS = (513, 527)      # 眼镜横梁（生成器里画在 512–528），故意压在虹膜盘上
ALL = {k: 1.0 for k in ENH.SUBS}


def _img(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))


def _face_backend():
    F = pytest.importorskip("mediapipe", reason="没有 mediapipe：几何语义用例无从校起")
    from lumaretouch_engine import face as FAC
    try:
        return FAC.build("mediapipe")
    except FAC.MissingBackend as e:
        pytest.skip(f"mediapipe 后端不可用：{e}")


_CACHE: dict = {}


def _detect(path, scale=1.0):
    """真后端跑一次并按需缩放（低光臂复用同一批关键点：几何没变，变的只是像素）。"""
    key = (path, scale)
    if key not in _CACHE:
        fx = _face_backend()
        im = _img(path).astype(np.float64) / 255.0
        if scale != 1.0:
            im = np.clip(im * scale, 0.0, 1.0)
        det = np.clip(im * 255.0, 0, 255).astype(np.uint8)
        pc = fx(det)
        assert pc.landmarks.shape == (478, 3), pc.landmarks.shape
        _CACHE[key] = (im, pc.landmarks)
    return _CACHE[key]


def _field(path, scale=1.0):
    im, lm = _detect(path, scale)
    h, w = im.shape[:2]
    reg = ENH.geometry(lm, h, w)
    y0, x0, fh, fw = reg.window
    weight, facts = ENH.refine(reg, im[y0:y0 + fh, x0:x0 + fw])
    return im, reg, (weight, facts)


# ---------------------------------------------------------------- 参数校验
def test_check_amounts_accepts_partial_and_clamps_types():
    assert ENH.check_amounts({"iris": 0.5}) == {**dict.fromkeys(ENH.AMOUNT_KEYS, 0.0), "iris": 0.5}
    assert ENH.check_amounts({}) == {k: 0.0 for k in ENH.AMOUNT_KEYS}


@pytest.mark.parametrize("bad", [
    {"iris": float("nan")}, {"iris": float("inf")}, {"iris": -0.01}, {"iris": 1.01},
    {"iris": "abc"}, {"eyebrow": 0.5}, ["iris"], {"iris": None},
])
def test_check_amounts_rejects_each_shape_of_bad_input(bad):
    with pytest.raises(ENH.EnhanceError):
        ENH.check_amounts(bad)


def test_is_identity_requires_valid_values():
    assert ENH.is_identity({"iris": 0.0}) is True
    with pytest.raises(ENH.EnhanceError):
        ENH.is_identity({"iris": 2.0})       # 非法不是"没活"，是"要拒"


def test_landmarks_must_be_normalized_not_pixels():
    """把已经是像素的点再乘一次要当场响，而不是画一张跑到画布外的掩膜。"""
    lm = np.zeros((478, 3), dtype=np.float32)
    lm[:, 0] = 0.5
    lm[:, 1] = 0.4
    lm[ENH.IRIS_LEFT, 0] = 640.0            # 越界
    with pytest.raises(ENH.EnhanceError):
        ENH.geometry(lm, 800, 600)
    with pytest.raises(ENH.EnhanceError):
        ENH.geometry(np.zeros((468, 3)), 800, 600)          # 点数不合契约


# ---------------------------------------------------------------- 几何语义
def test_eye_ring_indices_mean_what_the_names_say():
    """LNX-PORTRAIT-009 用到的两条眼睑环，在真 MediaPipe 上必须真的是"围着虹膜的一圈"。"""
    im, lm = _detect(FIX_SMILE)
    h, w = im.shape[:2]
    pix = ENH._landmark_pixels(lm, h, w)
    for ring, iris, rim in ((ENH.EYE_RING_LEFT, ENH.IRIS_LEFT, ENH.IRIS_RIM_LEFT),
                            (ENH.EYE_RING_RIGHT, ENH.IRIS_RIGHT, ENH.IRIS_RIM_RIGHT)):
        poly = pix[list(ring)]
        cx, cy = pix[iris]
        assert len(set(ring)) == 16 and len(set(poly[:, 0]) | set(poly[:, 1])) > 8, ring
        # 虹膜中心必须在环内（绕数法，与 _star_ok 的射线法相互独立）
        wn = 0
        for i in range(len(poly)):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % len(poly)]
            if ay <= cy < by and (bx - ax) * (cy - ay) - (cx - ax) * (by - ay) > 0:
                wn += 1
            elif by <= cy < ay and (bx - ax) * (cy - ay) - (cx - ax) * (by - ay) < 0:
                wn -= 1
        assert wn != 0, f"虹膜中心不在自己的眼睑环里（绕数 {wn}）：下标认错部位了"
        assert int((poly[:, 1] < cy).sum()) >= 2 and int((poly[:, 1] > cy).sum()) >= 2, \
            "眼睑环必须上下都有点：只有一边说明这条链是半圈"
        assert ENH._star_ok(poly, cx, cy) is None
        r = float(np.hypot(pix[list(rim), 0] - cx, pix[list(rim), 1] - cy).mean())
        assert 6.0 < r < 200.0, f"虹膜半径 {r} px 不像话"


def test_lip_chain_indices_mean_what_the_names_say():
    """两条唇链：过 0 的那条必须在嘴角连线**之上**，过 17 的那条必须在**之下**。"""
    im, lm = _detect(FIX_SMILE)
    h, w = im.shape[:2]
    pix = ENH._landmark_pixels(lm, h, w)
    line_y = float(pix[ENH.MOUTH_CORNER_LEFT, 1] + pix[ENH.MOUTH_CORNER_RIGHT, 1]) / 2.0
    up_y = float(pix[list(ENH.LIP_CHAIN_UPPER)][:, 1].mean())
    lo_y = float(pix[list(ENH.LIP_CHAIN_LOWER)][:, 1].mean())
    assert up_y < line_y < lo_y, (up_y, line_y, lo_y)
    assert pix[ENH.LIP_INNER_TOP, 1] < pix[ENH.LIP_INNER_BOTTOM, 1]   # 13 在 14 上方
    # 嘴角必须是唇簇的最左与最右（否则"嘴宽"就不是嘴宽）
    mouth = pix[list(ENH.LIP_CHAIN_UPPER) + list(ENH.LIP_CHAIN_LOWER)]
    assert abs(float(mouth[:, 0].min()) - float(pix[ENH.MOUTH_CORNER_LEFT, 0])) < 1.0
    assert abs(float(mouth[:, 0].max()) - float(pix[ENH.MOUTH_CORNER_RIGHT, 0])) < 1.0
    # 这条环必须是「从左嘴角 61 过上唇到右嘴角 291，再穿过下唇回到 61」的一圈：
    # 20 个点、一个都不重复（重复点会造出零长边，射线求交随之退化），首尾分别是两个嘴角。
    # 上一版这里写成 `... or True`，于是这条断言永真——那就是「只会通过的校验」本身。
    ring = list(ENH.LIP_CHAIN_UPPER) + list(ENH.LIP_CHAIN_LOWER)[-2:0:-1]
    assert len(ring) == 20 and len(set(ring)) == 20, ring
    assert ring[0] == ENH.MOUTH_CORNER_LEFT, ring
    assert ring[len(ENH.LIP_CHAIN_UPPER) - 1] == ENH.MOUTH_CORNER_RIGHT, ring
    cx = float(pix[ENH.MOUTH_CORNER_LEFT, 0] + pix[ENH.MOUTH_CORNER_RIGHT, 0]) / 2.0
    cy = line_y
    assert ENH._star_ok(pix[ring], cx, cy) is None


def test_base_fixture_is_a_closed_mouth_and_refuses_teeth():
    """闭嘴样本不硬画牙齿：整层不点火，而且说得出原因（这是"不支持要显式"的那一半）。"""
    im, reg, (weight, facts) = _field(FIX_BASE)
    open_ = reg.info["mouth"]["openness"]
    assert open_ < ENH.MOUTH_OPEN_MIN, f"这张夹具本来该是闭嘴，实测开口度 {open_}"
    assert facts["teeth"]["reason"] and "闭嘴" in facts["teeth"]["reason"], facts["teeth"]
    assert float(weight[2].max()) == 0.0


# ---------------------------------------------------------------- 栅格化正确性
def test_star_weight_matches_an_analytic_square():
    """星形栅格化对一个已知多边形必须给出已知形状（解析真值，不看图片）。"""
    side = 40.0
    poly = np.array([[0.0, 0.0], [side, 0.0], [side, side], [0.0, side]])
    ys, xs = np.mgrid[0:60, 0:60]
    w = ENH._star_weight(xs.astype(float), ys.astype(float), side / 2, side / 2, poly, 0.0)
    inside = (xs >= 0) & (xs <= side) & (ys >= 0) & (ys <= side)
    assert int((w[~inside.astype(bool)] > 0).sum()) == 0
    # 内部离边界 ≥ 2 px 的地方必须满额度（软边只允许出现在边上）
    core = inside & (xs >= 2) & (xs <= side - 2) & (ys >= 2) & (ys <= side - 2)
    assert float(w[core].min()) == 1.0


@pytest.mark.parametrize("poly,why", [
    # 一个十字：从中心出发的某些射线会交 3 次 → 不是星形
    (np.array([[10, 0], [20, 10], [30, 10], [40, 20], [30, 30], [20, 30],
               [10, 30], [0, 20], [10, 10], [20, 10]]), None),
])
def test_star_ok_rejects_a_non_star_shaped_polygon(poly, why):
    """守卫要能负向自证：拿一个非星形多边形去撞，它必须给出理由而不是放行。

    这条用例存在的理由与本仓所有"校验"同一句话：只会通过的校验等于没有校验。
    """
    r = ENH._star_ok(poly, 20.0, 20.0, rays=72)
    assert r is not None and "星形" in r, f"这个非星形多边形被放行了：{r!r}"


def test_star_ok_rejects_a_polygon_that_does_not_wind_once():
    poly = np.array([[25.0, 20.0], [25.0, 25.0], [20.0, 25.0]])    # 中心在多边形外
    r = ENH._star_ok(poly, 0.0, 0.0, rays=36)
    assert r is not None, "中心不在多边形里却没有拒"


def test_weight_is_exactly_zero_outside_the_region_window():
    """掩膜只可能落在几何顶点包围盒里：外面是 0，不是"很小"。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    assert fh > 0 and fw > 0
    assert weight.shape == (3, fh, fw)
    assert float(weight[:, 0, 0].min()) >= 0.0 and float(weight.max()) <= 1.0


# ---------------------------------------------------------------- 三条构造性质
def test_hue_is_never_touched_in_float():
    """冻结件"无虹膜意外改色"的结构形式：本层不进入 h 这个量。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    out = ENH.enhance_np(sub, weight, ALL)
    h_in = rgb_to_hsv_np(np.clip(sub, 0, 1))[..., 0]
    h_out = rgb_to_hsv_np(np.clip(out, 0, 1))[..., 0]
    assert float(np.abs(h_out - h_in).max()) <= 1e-12, \
        f"色相被改了 {float(np.abs(h_out - h_in).max())}"


def test_neutral_pixels_cannot_be_tinted():
    """s=0 的中性像素（眼镜框、高光、白墙）在乘性式下恒等于自己。"""
    im, reg, (weight, facts) = _field(FIX_GLASS)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    neutral = rgb_to_hsv_np(np.clip(sub, 0, 1))[..., 1] <= 1e-9
    assert int(neutral.sum()) > 0, "这张图里没有中性像素，用例失去意义"
    out = ENH.enhance_np(sub, weight, ALL)
    s_out = rgb_to_hsv_np(np.clip(out, 0, 1))[..., 1]
    assert float(s_out[neutral].max()) == 0.0, "中性像素被上色了"


def test_glasses_bar_gets_zero_eye_weight():
    """横梁压在虹膜盘上：虹膜与眼白两道门都必须把它整块掉出去（一手实测 w_max=0）。"""
    im, reg, (weight, facts) = _field(FIX_GLASS)
    y0, x0, fh, fw = reg.window
    bar = weight[:, GLASS_BAR_ROWS[0] - y0:GLASS_BAR_ROWS[1] - y0, :]
    assert float(bar[1].max()) == 0.0, f"眼镜横梁上还留着虹膜额度 {float(bar[1].max())}"
    assert float(bar[0].max()) == 0.0, f"眼镜横梁上还留着眼白额度 {float(bar[0].max())}"


def test_overexposure_guard_is_per_pixel():
    """"牙齿过曝"落成逐像素不变量：不加深、不越过 max(原值, 天花板)、已够亮的像素不动。"""
    for path, scale in ((FIX_SMILE, 1.0), (FIX_GLASS, 1.0), (FIX_DEEP, 1.0), (FIX_SMILE, 0.45)):
        im, reg, (weight, facts) = _field(path, scale)
        y0, x0, fh, fw = reg.window
        sub = im[y0:y0 + fh, x0:x0 + fw]
        out = ENH.enhance_np(sub, weight, ALL)
        v_in = rgb_to_hsv_np(np.clip(sub, 0, 1))[..., 2]
        v_out = rgb_to_hsv_np(np.clip(out, 0, 1))[..., 2]
        assert np.all(v_out >= v_in - 1e-12), "这一层里有像素被推暗了"
        assert np.all(v_out <= np.maximum(v_in, ENH.V_CEIL) + 1e-12), "有像素越过了天花板"
        above = v_in >= ENH.V_CEIL
        if int(above.sum()):
            assert np.allclose(v_out[above], v_in[above]), "已经比天花板亮的像素被动了"
        # 8 bit 上看不到新的剪切：255 的像素数不许增加
        q_in = np.round(np.clip(sub * 255.0, 0, 255)).astype(np.uint8)
        q_out = np.round(np.clip(out * 255.0, 0, 255)).astype(np.uint8)
        assert int((q_out.max(-1) >= 255).sum()) >= int((q_in.max(-1) >= 255).sum())
        assert int((q_out.max(-1) >= 255).sum()) - int((q_in.max(-1) >= 255).sum()) <= 0, \
            f"{path}×{scale}：满档把 {int((q_out.max(-1) >= 255).sum())} 格推到 255"


def test_desaturation_only_ever_gets_lighter():
    """眼白/牙齿的去黄是乘性下降：不会反转，也不会把饱和推到负值之外。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    s_in = rgb_to_hsv_np(np.clip(sub, 0, 1))[..., 1]
    for amt in (0.4, 1.0):
        out = ENH.enhance_np(sub, weight, {"sclera": amt, "teeth": amt})
        s_out = rgb_to_hsv_np(np.clip(out, 0, 1))[..., 1]
        m = (weight[0] > 0.5) | (weight[2] > 0.5)
        assert np.all(s_out[m] <= s_in[m] + 1e-12), "去黄那一格把饱和推高了"
        assert float(s_out.min()) >= 0.0


def test_teeth_mask_lands_on_the_teeth_the_fixture_painted():
    """接地真相：每一个牙齿额度 ≥ 0.5 的格子，**它自己的像素**得真的是牙色。

    带子不写行号也不按行平均，逐格判：牙=亮而淡、唇=红、腔=暗。上一版把生成器里
    画牙缝那两条 `line` 的 750–774 / 790–804 当成了牙带，实测那 439 格“越界”根本不是
    越界——它们是 `rounded_rectangle` 真画到 748 与 806 的牙齿。再上一版改成按行平均
    判，又被另一个画法细节骗了：龈缘那条 3 px 的暗线只画到 CX±68，而牙带画到 CX±70，
    于是行 773 被归为“唇面”，而它那 2 格满额度其实是牙。**逐格判才不留这种口。**
    """
    im, reg, (weight, facts) = _field(FIX_SMILE)
    h, w = im.shape[:2]
    hsv = rgb_to_hsv_np(np.clip(im, 0.0, 1.0))
    s, v = hsv[..., 1], hsv[..., 2]
    pale = (v > 0.70) & (s < 0.25)                  # 牙：亮而淡
    lip_red = (s > 0.30) & (v > 0.45)               # 唇面：红且不够暗
    cavity = v < 0.35                                # 口腔阴影/龈缘暗线
    # “牙得被接住”那一半只能在 13/14 与两个嘴角夹出的那个小盒子里说：整张图的浅色皮肤同样满足
    # “亮而淡”（实测 pale 在全图有 771886 格），拿全图去要求覆盖率就是把判据写飘了。
    _im, lm = _detect(FIX_SMILE)
    pix = ENH._landmark_pixels(lm, h, w)
    ys_in = sorted(float(pix[i, 1]) for i in (ENH.LIP_INNER_TOP, ENH.LIP_INNER_BOTTOM))
    xs_in = sorted(float(pix[i, 0]) for i in (ENH.MOUTH_CORNER_LEFT, ENH.MOUTH_CORNER_RIGHT))
    box = np.zeros((h, w), dtype=bool)
    box[int(ys_in[0]):int(ys_in[1]) + 1, int(xs_in[0]):int(xs_in[1]) + 1] = True
    pale_mouth = pale & box
    assert int(pale_mouth.sum()) > 2000 and int(lip_red.sum()) > 2000, (
        int(pale_mouth.sum()), int(lip_red.sum()))   # 分类本身得站得住

    y0, x0, fh, fw = reg.window
    canvas = np.zeros((h, w), dtype=np.float32)
    canvas[y0:y0 + fh, x0:x0 + fw] = weight[2]
    lit = canvas > 0.5
    assert int(lit.sum()) >= 500, f"牙齿门只留下 {int(lit.sum())} px"
    bad = lit & ~pale
    rows_bad = sorted(set(np.where(bad)[0].tolist()))[:8]
    assert int(bad.sum()) == 0, (
        f"牙齿掩膜有 {int(bad.sum())} 格不是牙色（行 {rows_bad}）：那就是越界")
    assert float(canvas[lip_red].max()) == 0.0, (
        f"唇面像素上有牙齿额度 {float(canvas[lip_red].max()):.3f}：那会把嘴唇涂白")
    assert float(canvas[cavity].max()) == 0.0, (
        f"口腔阴影/龈缘上有牙齿额度 {float(canvas[cavity].max()):.3f}：把阴影提亮就是把嘴涂糊")
    # 反向：盒子内的真牙得被掩膜接住——只判“不外泄”会退化成“掩膜为空也绿”
    miss = pale_mouth & (canvas <= 0.5)
    assert int(miss.sum()) < 0.35 * int(pale_mouth.sum()), (
        f"{int(miss.sum())}/{int(pale_mouth.sum())} 格真牙齿没被掩膜接住：那一格就是假滑块")


def test_the_glasses_bar_really_lies_on_both_iris_discs():
    """护住“眼镜不沾光”那一臂的接地前提：横梁必须在两只眼的虹膜盘上都有中性格。

    实测（从夹具自己算）：横梁画在 512–528 行、CX±190，左虹膜中心在 528 行——正好
    压住圆心；右眼圆心在 530 行，横梁盖的是虹膜盘的**上半**。所以判据按这个写：
    每只眼在圆心 ±20 列、横梁行带里都要有一块“中性中灰”（s<0.10 且 0.5<v<0.72），
    而同一块位置在未戴眼镜那张上不许有——不然“横梁挡住虹膜”是个空前提。
    """
    _im, lm_g = _detect(FIX_GLASS)
    h, w = _im.shape[:2]

    def _cls(path):
        im = _img(path).astype(np.float64) / 255.0
        hsv = rgb_to_hsv_np(np.clip(im, 0.0, 1.0))
        return (hsv[..., 1] < 0.10) & (hsv[..., 2] > 0.50) & (hsv[..., 2] < 0.72)

    bar_g, bar_b = _cls(FIX_GLASS), _cls(FIX_SMILE)
    pix = ENH._landmark_pixels(lm_g, h, w)
    for name, iris in (("左", ENH.IRIS_LEFT), ("右", ENH.IRIS_RIGHT)):
        ix = int(round(float(pix[iris, 0])))
        box = (slice(GLASS_BAR_ROWS[0], GLASS_BAR_ROWS[1] + 1), slice(ix - 20, ix + 21))
        got, base = int(bar_g[box].sum()), int(bar_b[box].sum())
        assert got >= 200, f"{name}眼：横梁在虹膜盘上只留下 {got} 格中性中灰，前提不成立"
        assert base <= max(20, 0.1 * got), (
            f"{name}眼：未戴眼镜那张在同一块就有 {base} 格，判据分不开两者")


@pytest.mark.parametrize("path,scale,min_lsb", [
    (FIX_SMILE, 1.0, 8.0),        # 露齿：满档在牙齿上真的动得起来
    (FIX_SMILE, 0.45, 20.0),      # 低光
    (FIX_DEEP, 1.0, 8.0),         # 深肤色
    (FIX_GLASS, 1.0, 8.0),        # 眼镜
])
def test_not_a_fake_slider(path, scale, min_lsb):
    """DoD"严禁假滑块"在这一层的落点：满档必须在自己的掩膜上量出可见的 LSB 差。"""
    im, reg, (weight, facts) = _field(path, scale)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    out = ENH.enhance_np(sub, weight, ALL)
    d = np.abs(out - sub).max(-1) * 255.0
    tm = weight[2] > 0.5
    assert int(tm.sum()) > 0, (path, scale, facts["teeth"])
    lift = float(d[tm].mean())
    assert lift >= min_lsb, f"{Path(path).name} ×{scale}：牙齿那一格只动了 {lift:.2f} LSB"


def test_each_sub_only_moves_its_own_pixels():
    """冻结件"每子功能独立启停"：只开一格时，它自己的权重为 0 的地方必须逐字节不动。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    for i, k in enumerate(ENH.SUBS):
        if float(weight[i].max()) == 0.0:
            continue
        out = ENH.enhance_np(sub, weight, {k: 1.0})
        untouched = weight[i] <= 0.0
        assert np.array_equal(out[untouched], sub[untouched]), \
            f"只开 {k} 却动了它权重为 0 的像素：独立启停不成立"
    zero = ENH.enhance_np(sub, weight, {k: 0.0 for k in ENH.SUBS})
    assert np.array_equal(zero, sub), "三个数全 0 却没回到原图"


def test_amount_scaling_is_monotone_on_teeth():
    """同一格推大不该出现"回头看"：牙齿的亮度均值随档位单调不降。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    tm = weight[2] > 0.5
    prev = -1.0
    for a in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        out = ENH.enhance_np(sub, weight, {"teeth": a})
        mean = float(rgb_to_hsv_np(np.clip(out, 0, 1))[..., 2][tm].mean())
        assert mean >= prev - 1e-12, f"teeth={a} 比上一档更暗：不是连续的可控量"
        prev = mean


# ---------------------------------------------------------------- 两臂对拍
def test_numpy_arm_and_torch_arm_agree():
    """生产臂与解析臂逐点一致（容差给 float32 的舍入，不给"算法不同"留地方）。"""
    pytest.importorskip("torch", reason="没有 torch：生产臂不在这一台机器上")
    import torch

    from lumaretouch_engine.ops import enhance as E
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    np_out = ENH.enhance_np(sub, weight, {k: 0.8 for k in ENH.SUBS})
    t_in = torch.from_numpy(np.ascontiguousarray(sub.transpose(2, 0, 1)))[None].float()
    t_w = torch.from_numpy(weight).float()
    for dev in (["cpu"] + (["cuda"] if torch.cuda.is_available() else [])):
        got = E.enhance_t(t_in.to(dev), t_w.to(dev), {k: 0.8 for k in ENH.SUBS})
        arr = got[0].cpu().numpy().transpose(1, 2, 0)
        assert float(np.abs(arr - np_out).max() * 255.0) <= 0.05, (dev, float(
            np.abs(arr - np_out).max() * 255.0))


def test_torch_arm_short_circuits_at_neutral():
    """全 0 时生产臂必须**递回同一个张量对象**：一个算子也不跑（与 grade 同构）。"""
    torch = pytest.importorskip("torch")
    t = torch.zeros((1, 3, 8, 8), device="cpu")
    w = np.ones((3, 8, 8), dtype=np.float32)
    assert ENH.enhance_t(t, torch.from_numpy(w), {k: 0.0 for k in ENH.SUBS}) is t


# ---------------------------------------------------------------- 会话层
def test_pipeline_apply_touches_only_the_window():
    """vram 的写回路径：窗口外的像素是**复制**过去的，逐字节不变。

    这里走的是产品那条路（load_rgb_u8 → build_enhance(真关键点) → apply_enhance），
    不手搭 `enhance_*` 字段：手搭的那一份会跟着字段改名一起安静失效，而且测的不是
    真实入口——上一版还把关键点按 `edge / w` 缩放（缩小方向写反），窗口退化成角落一块，
    「只动窗口」这条也就跟着变成了自证。
    """
    pytest.importorskip("torch", reason="会话层需要 torch")

    from lumaretouch_engine.vram import PreviewPipeline

    im, lm = _detect(FIX_SMILE)
    h, w = im.shape[:2]
    pipe = PreviewPipeline("cpu", w, h)
    pipe.load_rgb_u8(np.clip(im * 255.0, 0, 255).astype(np.uint8))
    built = pipe.build_enhance(lm)
    # 建了场而三个数还是 0：lit 必须如实说 false（面板那句「已生效」跟着它，不跟命令）
    assert built["enhance_built"] is True and built["enhance_lit"] is False, built
    assert built["enhance_build_ms"] > 0.0, built          # 一次性账是实测，不是占位 0
    assert sum(built["enhance_gated_px"].values()) > 0, built
    pipe.set_enhance({k: 1.0 for k in ENH.SUBS})
    assert pipe.has_enhance() is True
    src = pipe.src_f32
    out = pipe.apply_enhance(src)
    ly0, lx0, lh, lw = pipe.enhance_local
    assert lh > 0 and lw > 0
    outside = np.ones((h, w), dtype=bool)
    outside[ly0:ly0 + lh, lx0:lx0 + lw] = False
    a = src[0].permute(1, 2, 0).cpu().numpy()
    b = out[0].permute(1, 2, 0).cpu().numpy()
    assert np.array_equal(a[outside], b[outside]), "窗口外被改动了"
    assert float(np.abs(a - b).max()) > 0.0, "点火了却一格没动：这一层挂的是空场"
    assert pipe.enhance_resident_bytes() > 0, "常驻账单报了 0，而这一层确实持有权重场"
    # 整层放下：场与参数都归零，之后 apply 必须**递回同一个张量对象**（一个算子也不跑）
    pipe.clear_enhance()
    assert pipe.apply_enhance(src) is src
    assert pipe.enhance_resident_bytes() == 0, "放下之后还常驻着权重场"
    assert pipe.has_enhance() is False


def test_session_short_circuit_when_no_field():
    pytest.importorskip("torch", reason="会话层需要 torch")
    import torch

    from lumaretouch_engine.vram import PreviewPipeline
    pipe = PreviewPipeline("cpu", 32, 32)
    pipe.load_rgb_u8(np.zeros((32, 32, 3), dtype=np.uint8))
    t = pipe.src_f32
    pipe.set_enhance({k: 1.0 for k in ENH.SUBS})
    assert pipe.has_enhance() is False          # 参数点火而场为空：如实说没活
    assert pipe.apply_enhance(t) is t


def test_set_enhance_field_crops_to_the_tile_origin():
    """导出分块的挂场入口：按画布原点求交，块外整层不挂而不是贴错位。"""
    pytest.importorskip("torch", reason="会话层需要 torch")
    from lumaretouch_engine.vram import PreviewPipeline
    pipe = PreviewPipeline("cpu", 40, 40)
    pipe.load_rgb_u8(np.zeros((40, 40, 3), dtype=np.uint8))
    w = np.ones((3, 20, 20), dtype=np.float32)
    # 场在画布 (y0=50,x0=50)，而本会话从 (0,0) 起、只有 40×40：求交后什么都不该挂上
    pipe.set_enhance_field((50, 50, 20, 20), w, origin=(0, 0))
    assert pipe.enhance_gpu is None
    assert pipe.enhance_local is None and pipe.enhance_window is None
    # 本会话从画布 (20,20) 起：应挂到局部 (10,10) 起、尺寸 20×20
    pipe.set_enhance_field((30, 30, 20, 20), w, origin=(20, 20))
    assert pipe.enhance_local == (10, 10, 20, 20), pipe.enhance_local
    assert pipe.enhance_gpu.shape == (3, 20, 20)
    with pytest.raises(ValueError):
        pipe.set_enhance_field((0, 0, 5, 5), w)          # 形状与窗口不合


def test_refine_reports_hands_facts_not_just_success():
    """每子功能都要报得出"几何多少格 / 门后多少格 / 没点火是为什么"。"""
    for path in (FIX_SMILE, FIX_GLASS, FIX_DEEP):
        im, reg, (weight, facts) = _field(path)
        for k in ENH.SUBS:
            f = facts[k]
            assert {"geom_px", "gated_px", "reason"} <= set(f), (path, k, f)
            assert f["gated_px"] <= f["geom_px"], (path, k, f)
        assert facts["teeth"]["kept_px"] > 0, (path, facts["teeth"])


def test_low_light_and_deep_skin_keep_working_by_relative_criteria():
    """内容门不许写绝对阈值：暗一档与深肤色一档都还得在牙上留下额度。"""
    im, reg, (w1, f1) = _field(FIX_SMILE)
    _im, _r, (w2, f2) = _field(FIX_SMILE, 0.45)
    _im, _r, (w3, f3) = _field(FIX_DEEP)
    assert f1["teeth"]["gated_px"] > 0 and f2["teeth"]["gated_px"] > 0 \
        and f3["teeth"]["gated_px"] > 0, (f1["teeth"], f2["teeth"], f3["teeth"])
    # 相对判据的直接后果：暗一档的池均值明显更低，而点火像素数量级不变
    assert f2["teeth"]["pool_v_mean"] < 0.5 * f1["teeth"]["pool_v_mean"], \
        (f1["teeth"], f2["teeth"])
    assert abs(f2["teeth"]["gated_px"] - f1["teeth"]["gated_px"]) < 0.6 * f1["teeth"]["gated_px"]


def test_iris_saturation_gain_is_multiplicative_and_capped():
    """虹膜：饱和乘性上升、上限夹住、不许顶到 1.0 造成断层。"""
    im, reg, (weight, facts) = _field(FIX_SMILE)
    y0, x0, fh, fw = reg.window
    sub = im[y0:y0 + fh, x0:x0 + fw]
    out = ENH.enhance_np(sub, weight, {"iris": 1.0})
    s_in = rgb_to_hsv_np(np.clip(sub, 0, 1))[..., 1]
    s_out = rgb_to_hsv_np(np.clip(out, 0, 1))[..., 1]
    m = weight[1] > 0.5
    assert float(s_out[m].mean()) > float(s_in[m].mean()), "虹膜满档没让饱和动过"
    assert np.all(s_out[m] <= np.maximum(s_in[m], ENH.IRIS_S_CEIL) + 1e-12), "越过饱和天花板"
    assert np.all(s_out[m] >= s_in[m] - 1e-12), "虹膜那一格把饱和推低了"


def _pip_inside(poly, px: float, py: float) -> bool:
    """绕数法点在多边形内：与本模块那套克莱默射线求交**独立**，才能当参考解。"""
    wn = 0
    n = len(poly)
    for i in range(n):
        ax, ay = float(poly[i][0]), float(poly[i][1])
        bx, by = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        if ay <= py < by and (bx - ax) * (py - ay) - (px - ax) * (by - ay) > 0:
            wn += 1
        elif by <= py < ay and (bx - ax) * (py - ay) - (px - ax) * (by - ay) < 0:
            wn -= 1
    return wn != 0


def _dist_to_boundary(poly, px, py):
    """到多边形边界的最短距离（逐边段点到线段）：用来把「深里」与「边上」分开。"""
    d = np.full(px.shape, np.inf)
    n = len(poly)
    for i in range(n):
        ax, ay = float(poly[i][0]), float(poly[i][1])
        ex, ey = float(poly[(i + 1) % n][0]) - ax, float(poly[(i + 1) % n][1]) - ay
        s = np.clip(((px - ax) * ex + (py - ay) * ey) / max(ex * ex + ey * ey, 1e-12), 0.0, 1.0)
        d = np.minimum(d, np.hypot(px - (ax + s * ex), py - (ay + s * ey)))
    return d


def test_star_weight_is_exact_against_a_winding_number_reference():
    """栅格化必须等于多边形内部：既不外扩也不内缩（feather=0 的硬边口径）。

    外扩 = 掩膜爬到几何部位之外（“越界”那句 then），内缩 = 该增强的部位缺了一块
    （那才是假滑块该有的形状）。两个方向都要判：只判一个的校验等于半个校验。
    多边形按均分极角 + 小抖动生成（相邻边张角始终 < π），因此对中心必然星形——
    这一条由 `_star_ok` 自己当场核对，不靠构造推论。
    """
    rng = np.random.default_rng(20261018)
    n = 14
    step = 2.0 * math.pi / n
    trials = 0
    g = np.linspace(-70.0, 70.0, 61)
    for _ in range(8):
        angles = np.sort(np.arange(n) * step + rng.uniform(-0.4, 0.4, n) * step)
        radii = rng.uniform(20.0, 60.0, n)
        poly = np.stack([radii * np.cos(angles), radii * np.sin(angles)], axis=1)
        assert ENH._star_ok(poly, 0.0, 0.0) is None, "生成器得先保证它真的是星形"
        ys, xs = np.meshgrid(g, g)
        w = ENH._star_weight(xs, ys, 0.0, 0.0, poly, 0.0)
        ref = np.zeros(xs.shape, dtype=bool)
        for i in range(xs.shape[0]):
            for j in range(xs.shape[1]):
                ref[i, j] = _pip_inside(poly, float(xs[i, j]), float(ys[i, j]))
        leak = int((w[~ref] > 0).sum())
        assert leak == 0, f"多边形外有 {leak} 格拿到额度：掩膜又外扩了"
        deep = ref & (_dist_to_boundary(poly, xs, ys) >= 2.0)
        assert float(w[deep].min()) == 1.0, "内部离边界 2 px 处没给满额度：那就是内缩"
        trials += 1
    assert trials == 8, f"只跑了 {trials} 张：这个用例差点什么都没测就绿了"


def test_window_contains_the_whole_soft_edge_of_every_region():
    """羽化必须在窗口里就归零：窗口边界那一行/列不许有非 0 权重。

    非 0 就意味着软边被窗口边界硬切了一刀——那不是“越界”，是另一回事：嘴角上会
    留下一道笔直的生硬边界。唇环的 feather = 0.05×嘴宽（实量 15 px）比旧的固定
    外扩 6 px 大，所以这一条先红后绿，不是拍上来的。
    """
    for path in (FIX_SMILE, FIX_GLASS, FIX_DEEP, FIX_BASE):
        im, reg, (weight, facts) = _field(path)
        edges = {"首行": (slice(None), 0, slice(None)), "末行": (slice(None), -1, slice(None)),
                 "首列": (slice(None), slice(None), 0), "末列": (slice(None), slice(None), -1)}
        for name, sl in edges.items():
            got = float(weight[sl].max())
            assert got == 0.0, f"{Path(path).name}：窗口{name}上还留着 {got:.3f} 的权重"
