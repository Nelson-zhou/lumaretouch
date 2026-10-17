"""M1-4 消除笔：修补算子的数值保真 + 常驻修补图层的生命周期。

分两层是刻意的：`ops/inpaint` 有独立的 CPU 参考实现，所以**没装 torch 的 CI job 也能验**
它的算法性质（还原精度、不变式、参数边界）；常驻图层那部分必须有 torch。

主张与验收的对应关系：
* 「只改画到的地方」→ 笔外逐字节相等（不是容差）；
* 「修补确实有效」→ 孔内 MAE/PSNR 有绝对数值，且对"什么都不做"与"单尺度平均"两条基线都比得出优劣；
* 「GPU 能上生产」→ 与 float64 参考实现量化后差 ≤1 LSB；
* 「层数由洞决定」→ 直接做一个悬崖回归：按裁块算层数会明显变差，用例钉住正确的那个。
"""

from __future__ import annotations

import math
import os

import numpy as np
import pytest

try:
    import torch
except Exception:            # CI 的 CPU job 没装 torch：算子那部分本来就是纯 numpy，不能连它一起跳过
    torch = None
needs_torch = pytest.mark.skipif(torch is None, reason="常驻修补图层需要 torch")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = os.path.join(HERE, "tests", "fixtures", "portrait-1024x1280.png")

needs_fixture = pytest.mark.skipif(not os.path.isfile(PNG),
                                   reason="缺测试人像，先跑 packaging/make-test-portrait.py")


# ------------------------------------------------------------------ 小工具
def _smooth_image(h=96, w=120):
    """低频底图 + 一条跨洞的边缘：合成图上的还原精度可以算得干净（无随机性）。"""
    ys, xs = np.mgrid[0:h, 0:w]
    r = 0.55 + 0.10 * np.sin(xs / 9.0) + 0.07 * np.cos(ys / 11.0)
    g = 0.48 + 0.09 * np.sin(ys / 13.0)
    b = 0.42 + 0.06 * ((xs + ys) % 17) / 17.0
    edge = (xs > w // 2).astype(np.float64) * 0.12      # 一条竖直台阶，考验电导是否跨边
    img = np.stack([r, g, b], axis=0) + edge[None]
    return np.ascontiguousarray(img[None].astype(np.float64))


def _blob(h, w, cy, cx, r, dtype=np.float64):
    ys, xs = np.mgrid[0:h, 0:w]
    return ((((ys - cy) ** 2 + (xs - cx) ** 2) <= r * r).astype(dtype))[None, None]


def _load_fixture_u8():
    from PIL import Image

    a = np.asarray(Image.open(PNG).convert("RGB"))
    if a.shape[:2] == (1280, 1024):                     # 缩到产品代理档量级，CI 也跑得快
        a = np.array(Image.fromarray(a).resize((512, 640)))
    return a


# ============================================================ 算子层（纯 numpy）
def test_zero_weight_is_byte_identical():
    """不变式 1：没画笔画 = 一模一样。写反混合方向（`(1-w)*fill + w*img`）会当场红。"""
    from lumaretouch_engine.ops.inpaint import inpaint_np

    img = _smooth_image()
    w = np.zeros((1, 1) + img.shape[-2:], dtype=np.float64)
    out = inpaint_np(img, w, refine_iters=2)
    assert np.array_equal(out, img), "weight=0 时输出被改动了"


def test_pixels_outside_brush_are_byte_identical():
    """不变式 2：笔外的像素在结果里必须逐字节保持原值（羽化环也一样）。"""
    from lumaretouch_engine.ops.inpaint import inpaint_np

    img = _smooth_image(64, 80)
    w = _blob(64, 80, 32, 40, 7)
    out = inpaint_np(img, w, refine_iters=3)
    outside = w[0, 0] == 0
    assert np.array_equal(out[0][:, outside], img[0][:, outside]), "笔外像素被动过了"
    assert np.isfinite(out).all()


def test_hole_is_actually_filled_and_measurably_close():
    """「修补确实有效」要有绝对数：把干净图挖洞再补回去，量孔内误差。

    这里的地面真值就是原图：算法只看得到 `img*known`（洞内为 0），所以这不是
    "把原值抄回来"，而是从周围推出来。洞心正好压在合成图的那条竖直台阶上，
    所以这一档比真图皮肤更难（实测 7.8 LSB，真图 4.0 LSB）：跨边重建就是消除笔的难点。
    """
    from lumaretouch_engine.ops.inpaint import inpaint_np

    img = _smooth_image(64, 80)
    w = _blob(64, 80, 32, 40, 5)
    out = inpaint_np(img, w, refine_iters=4)
    inside = w[0, 0] > 0.5
    mae = float(np.abs(out[0][:, inside] - img[0][:, inside]).mean()) * 255.0
    assert mae < 12.0, f"孔内 MAE {mae:.2f} LSB：跨边台阶上都收不住，谈不上生产可用"
    # 与"什么都不做"（洞留着 0）比较：证明这一步真的在补，而不是报了个自洽的数
    naive = float(np.abs((img * (1 - w)) - img)[0][:, inside].mean()) * 255.0
    assert mae < naive / 5, f"只比基线好 {naive / max(mae, 1e-6):.1f}×，修补没起作用"


@needs_fixture
def test_quality_ordering_matches_the_design_claim():
    """三档基线排序必须成立：不动 < 单尺度平均 < 多尺度+扩散。

    这一条是"我们换来了什么"的对偶证据。如果哪天有人把 refine 或金字塔关掉，
    报表上只会少几个毫秒，而这里会红。
    """
    from lumaretouch_engine.ops.guided import _box_np
    from lumaretouch_engine.ops.inpaint import inpaint_np

    u8 = _load_fixture_u8()
    h, w = u8.shape[:2]
    img = np.ascontiguousarray((u8.astype(np.float64) / 255.0).transpose(2, 0, 1)[None])
    m = _blob(h, w, h // 2, w // 2, 7)
    single = _box_np(img * (1 - m), 10) / np.maximum(_box_np(1 - m, 10), 1e-6)
    inside = m[0, 0] > 0.5

    def mae(o):
        return float(np.abs(o[0][:, inside] - img[0][:, inside]).mean()) * 255.0

    plain = inpaint_np(img, m, smooth_iters=0, refine_iters=0)
    full = inpaint_np(img, m, smooth_iters=1, refine_iters=4)
    naive = float(np.abs((img * (1 - m)) - img)[0][:, inside].mean()) * 255.0   # 什么都不做：洞留 0
    assert mae(single) > mae(plain) >= mae(full) - 1e-9, \
        f"排序不成立：单尺度 {mae(single):.2f} / pushpull {mae(plain):.2f} / 全链 {mae(full):.2f}"
    assert mae(full) < 8.0, f"真图上孔内 MAE {mae(full):.2f} LSB，超过可用线"
    assert mae(full) < naive / 4, f"只比“什么都不做”好 {naive / max(mae(full), 1e-6):.1f}×，修补没真起作用"


def test_levels_come_from_the_hole_not_the_crop():
    """悬崖回归：洞相对裁块够大时，按幅面算层数会质变式变差。

    实测的层数-质量曲线（合成图与真图同形）：MAE 在 levels 达到 `ceil(log2(洞长))`
    之前陡降，之后就是平台——再深也不得好处。例：111×111 裁块上 45 px 的洞，
    4 层 20.4 LSB、6 层 7.8 LSB；7 层与 8 层都是 7.8。所以这里同时卡两条：
    不足层数必须明显更差，更深并不更好。
    """
    from lumaretouch_engine.ops.inpaint import (
        auto_levels, hole_extent, inpaint_np, levels_for, mask_bbox)

    h = w = 400
    img = _smooth_image(h, w)
    m = _blob(h, w, h // 2, w // 2, 22)                   # 45 px 的洞
    y0, y1, x0, x1 = mask_bbox(m[0, 0], pad=32, grow=1.5)  # 与 vram 重放路径同一裁块规则
    sub, ms = img[..., y0:y1, x0:x1], m[..., y0:y1, x0:x1]
    lv_crop = auto_levels(y1 - y0, x1 - x0)
    lv_right = levels_for(hole_extent(ms[0, 0]), y1 - y0, x1 - x0)
    assert lv_right > lv_crop, f"按洞算的层数没超过按幅面算的：{lv_right} vs {lv_crop}"
    inside = ms[0, 0] > 0.5

    def mae(lv):
        o = inpaint_np(sub, ms, levels=lv, smooth_iters=1, refine_iters=4)
        return float(np.abs(o[0][:, inside] - sub[0][:, inside]).mean()) * 255.0

    bad, good = mae(lv_crop), mae(lv_right)
    assert bad > good * 1.8, f"悬崖没复现：{lv_crop} 层 {bad:.1f} vs {lv_right} 层 {good:.1f} LSB"
    assert mae(lv_right + 2) > good - 0.6, "再深两层反而更好——“层数由洞定”的结论变了"
    assert good < 12.0, f"正确层数下仍有 {good:.1f} LSB，可用线变了要重写上面两条"


def test_illegal_inputs_are_refused():
    """库层边界：直接调 vram/跑靶的调用方不经过协议校验，所以这里必须有闸。"""
    from lumaretouch_engine.ops.inpaint import inpaint_np

    img = _smooth_image(32, 32)
    w = _blob(32, 32, 16, 16, 3)
    for bad, why in ((w * 2.0, "覆盖度 >1"), (w - 0.5, "覆盖度 <0"),
                     (np.zeros((1, 3, 32, 32)), "weight 不是单通道"),
                     (np.zeros((32, 32)), "weight 少了批次维")):
        with pytest.raises(ValueError):
            inpaint_np(img, bad)
        assert why
    with pytest.raises(ValueError, match="同精度"):
        inpaint_np(img, w.astype(np.float32))
    with pytest.raises(ValueError, match="refine_dt"):
        inpaint_np(img, w, refine_iters=2, refine_dt=0.3)   # 显式扩散超过 0.25 会发散


def test_mask_bbox_grows_with_the_hole_and_clips():
    from lumaretouch_engine.ops.inpaint import mask_bbox

    small = _blob(200, 200, 100, 100, 3)[0, 0]
    big = _blob(200, 200, 100, 100, 40)[0, 0]
    b_small, b_big = mask_bbox(small, pad=32), mask_bbox(big, pad=32)
    assert (b_small[1] - b_small[0]) == 2 * 3 + 1 + 2 * 32, f"小洞边距不对：{b_small}"
    assert (b_big[1] - b_big[0]) > 80 + 2 * 32, f"大洞没按半径扩：{b_big}"
    edge = _blob(64, 64, 2, 2, 6)[0, 0]                   # 贴边洞
    y0, y1, x0, x1 = mask_bbox(edge, pad=32)
    assert (y0, x0) == (0, 0) and y1 <= 64 and x1 <= 64, "贴边没夹住，越界裁块会直接抛"
    assert mask_bbox(np.zeros((32, 32), np.float32)) is None


def test_rle_roundtrip_and_rejects():
    """控制通道只传"有笔的地方"：一颗痘印几十条行程，而不是整幅 1 MB 文本。"""
    from lumaretouch_engine.ops.inpaint import mask_from_rle, mask_to_rle

    m = (_blob(64, 64, 32, 32, 5) * 255).astype(np.uint8)[0, 0]
    rle = mask_to_rle(m)
    assert 0 < len(rle) < 64 * 8, f"行程数异常：{len(rle)}"
    assert np.array_equal(mask_from_rle(rle, 64, 64), m), "RLE 往返不等"
    for bad in ([[0, 0, 1]], [[0, 0, 1, 256]], [[0, 0, 999, 1]], [[99, 0, 1, 1]], [[0, 60, 8, 1]]):
        with pytest.raises(ValueError):
            mask_from_rle(bad, 64, 64)


def test_mask_to_rle_vectorized_equals_naive():
    """向量化编码器必须与逐像素旧版**逐字相同**。

    为什么单独钉这一条：旧版是双层 Python 循环，实测 1024×1280 要 187 ms——比修补
    本身还贵一个量级，所以把它换成了“找行内变化点”。但往返测试（上面那条）只能
    盖住二值笔：多值（羽化边缘/衰减值）下“把相邻不等值合并了”这种错不会让往返失败，
    只会让引擎收到一个不一样的掩膜——报表现场看不出来。
    """
    from lumaretouch_engine.ops.inpaint import mask_to_rle

    def naive(a):
        out = []
        for y, row in enumerate(a):
            x, w = 0, row.shape[0]
            while x < w:
                v = int(row[x])
                if v == 0:
                    x += 1
                    continue
                e = x + 1
                while e < w and int(row[e]) == v:
                    e += 1
                out.append([y, x, e - x, v])
                x = e
        return out

    rng = np.random.default_rng(11)
    for trial in range(48):
        h = int(rng.integers(1, 24))
        w = int(rng.integers(1, 24))
        kind = trial % 4
        if kind == 0:                                    # 随机二值（行程多）
            a = (rng.integers(0, 2, (h, w)) * 255).astype(np.uint8)
        elif kind == 1:                                  # 三档灰度：相邻同值与异值交界
            a = (rng.integers(0, 3, (h, w)) * 127).astype(np.uint8)
        elif kind == 2:                                  # 圆笔印（产品实际形状）
            ys, xs = np.mgrid[0:h, 0:w]
            a = (((ys - h // 2) ** 2 + (xs - w // 2) ** 2) <= 9).astype(np.uint8) * 255
        else:                                            # 全随机逐像素：最坏情况
            a = (rng.random((h, w)) * 255).astype(np.uint8)
        got = mask_to_rle(a)
        assert got == naive(a), f"第 {trial} 次（{h}x{w} kind={kind}）与逐像素旧版不等"
    assert mask_to_rle(np.zeros((8, 8), np.uint8)) == []
    with pytest.raises(ValueError, match=r"\(H,W\)"):
        mask_to_rle(np.zeros((1, 1, 8, 8), np.uint8))


def test_feather_stays_in_range_and_does_not_reach_far():
    from lumaretouch_engine.ops.inpaint import feather_np

    m = (_blob(64, 64, 32, 32, 4) > 0).astype(np.float32)[0, 0]
    f = feather_np(m, 2)
    assert f.min() >= 0.0 and f.max() <= 1.0
    with pytest.raises(ValueError, match=r"\(H,W\)"):
        feather_np(f[None, None], 2)
    far = np.zeros((64, 64), np.float32)
    far[58, 58] = 1.0                                     # 远处一个点：羽化不该传到左上角
    assert feather_np(far, 2)[0, 0] == 0.0
    assert abs(float(f[m > 0].min()) - 1.0) < 0.34, "笔心应当接近满覆盖"


# ================================================== GPU 生产实现
@needs_torch
@needs_fixture
def test_gpu_matches_cpu_reference_within_one_lsb():
    """生产实现必须落在既定量产口径内：与 float64 参考差 ≤1 LSB（实测 ~0.33）。"""
    from lumaretouch_engine.ops.inpaint import inpaint_np, inpaint_t

    u8 = _load_fixture_u8()
    h, w = u8.shape[:2]
    arr32 = np.ascontiguousarray((u8.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
    m = _blob(h, w, h // 2, w // 2, 8)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    img_t = torch.from_numpy(arr32).to(dev)
    w_t = torch.from_numpy(np.ascontiguousarray(m.astype(np.float32))).to(dev)
    got = inpaint_t(img_t, w_t, smooth_iters=1, refine_iters=4)[0].cpu().numpy().astype(np.float64)
    ref = inpaint_np(arr32.astype(np.float64), m.astype(np.float64), smooth_iters=1, refine_iters=4)[0]
    q = lambda a: (np.clip(a, 0, 1) * 255).astype(np.uint8).astype(np.int16)
    diff = np.abs(q(got) - q(ref))
    assert diff.max() <= 1, f"GPU 与 CPU 参考差 {int(diff.max())} LSB，超出量产口径"
    assert float((diff > 0).mean()) < 0.05, f"{(diff > 0).mean():.1%} 子像素在差，1 LSB 掩盖了系统性偏差"


@needs_torch
def test_gpu_weight_range_and_nonfinite_are_refused():
    from lumaretouch_engine.ops.inpaint import inpaint_t

    img = torch.rand(1, 3, 48, 48)
    ok = torch.zeros(1, 1, 48, 48)
    ok[:, :, 20:30, 20:30] = 1.0
    with pytest.raises(ValueError, match=r"\[0,1\]"):
        inpaint_t(img, ok * 2.0)
    with pytest.raises(ValueError, match="形状"):
        inpaint_t(img, torch.zeros(1, 3, 48, 48))
    out = inpaint_t(img, ok)                              # 合法入参得跑通
    assert torch.isfinite(out).all() and out.shape == img.shape


# ============================================================ 常驻修补图层
@pytest.fixture
def fixture_rgb():
    from lumaretouch_engine.decode import load_rgb

    path = PNG if os.path.isfile(PNG) else os.path.join(HERE, "tests", "fixtures", "portrait-1024x1280.jpg")
    return load_rgb(path).rgb


@pytest.fixture
def session(fixture_rgb):
    from lumaretouch_engine.vram import make_pipeline

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return make_pipeline(dev, fixture_rgb.shape[1], fixture_rgb.shape[0], fixture_rgb)


def _op(pipe, cy, cx, r, op_id=1, **params):
    from lumaretouch_engine.vram import DEFAULT_REPAIR, RepairOp

    h, w = pipe.h, pipe.w
    weight = _blob(h, w, cy, cx, r, dtype=np.float32)[0, 0] * 255.0
    return RepairOp(op_id=op_id, weight=weight.astype(np.uint8),
                    params={**DEFAULT_REPAIR, **params})


@needs_torch
def test_repair_only_changes_pixels_inside_the_brush(session):
    before = session.base()
    info = session.add_repair(_op(session, session.h // 2, session.w // 2, 6))
    after = session.base()
    assert info["ops"] == 1 and info["applied"] == 1
    changed = (after - before)[0].abs().sum(0) > 0
    inside = torch.from_numpy((_op(session, session.h // 2, session.w // 2, 6)).weight > 0) \
        .to(after.device)
    assert bool((changed & ~inside).sum().item() == 0), "笔外的像素被改动了"
    assert int(changed.sum().item()) > 0, "笔内一点没改，等于消除笔空转"
    # 强度为 0 时也必须看得见修补：修的是底图，不是磨皮系数
    s0 = session.retouch(0.0)
    assert torch.equal(_to_chw_u8(s0), _to_chw_u8(session.base())), "strength=0 没把修补底图原样送出去"


@needs_torch
def test_repair_invalidates_filter_then_caches_again(session):
    """事件成本与逐帧成本必须分开：一次修补付一次滤波重算，之后拖滑块仍是零推理。"""
    session.retouch(0.5)                 # 第一帧本来就要建缓存
    session.retouch(0.5)
    assert session.last_filter_ms == 0.0
    session.add_repair(_op(session, 40, 40, 5))
    assert session.retouched is None, "加了一笔却没有作废滤波缓存——下一帧会拿旧底图的结果磨新底图"
    # M2-a：底图变了连分带也必须立即作废。只作废成品而留着分带，等于
    # “拿上一版脸的带磨这一版脸”：分带键里的修补版本号会隔手拦，但引用还挂在显存里，
    # 任何绕过键比较的调用方就会拿到旧带。
    assert session.bands is None, "加了一笔却没有作废分带缓存"
    session.retouch(0.5)
    assert session.last_filter_ms > 0.0, "底图变了却没重算滤波"
    assert session.last_bands_ms > 0.0, "底图变了却没重跑分带"
    assert session.filter_key[-1] == session.repair_version, "成品键没带修补版本号"
    assert session.bands_key[-1] == session.repair_version, "分带键没带修补版本号"
    for s in (0.5, 0.6, 0.75):
        session.retouch(s)
        assert session.last_filter_ms == 0.0, f"strength={s} 又重算滤波，修补把零推理弄丢了"


@needs_torch
def test_undo_redo_clear_are_byte_exact(session, fixture_rgb):
    src = session.base()
    a = session.add_repair(_op(session, 60, 60, 5, op_id=1))
    base_a = session.base().clone()
    b = session.add_repair(_op(session, session.h - 60, session.w - 60, 7, op_id=2))
    base_b = session.base().clone()
    assert not torch.equal(base_a, base_b), "第二笔没起作用"
    assert a["ops"] == 1 and b["ops"] == 2
    assert len(b["boxes"]) == 2, "两笔分开画应当各自裁块；合成一个大框等于裁块优势归零"

    u = session.undo_repair()
    assert u["ops"] == 1 and torch.equal(session.base(), base_a), "撤销后没回到上一笔"
    assert session.undo_repair()["ops"] == 0
    assert torch.equal(session.base(), src), "撤销全部笔迹后必须逐字节回到原图"
    assert session.undo_repair() is None, "空栈撤销不该返回成功"
    assert session.redo_repair()["ops"] == 1
    assert torch.equal(session.base(), base_a), "重做没复现第一笔"
    session.redo_repair()
    assert torch.equal(session.base(), base_b), "重做没复现第二笔"
    session.clear_repair(keep_redo=False)
    assert torch.equal(session.base(), src)
    assert session.redo_repair() is None, "keep_redo=False 应当连重做栈一起清掉"


@needs_torch
def test_new_session_replays_repair_ops(session, fixture_rgb):
    """换设备 = 新会话 + 按存下的画笔重放：结果应落在同一个字节口径内。"""
    from lumaretouch_engine.vram import make_pipeline

    ops = [session.add_repair(_op(session, 50, 50, 4, op_id=1)),
           session.add_repair(_op(session, session.h - 50, session.w - 50, 6, op_id=2))]
    gpu_base = session.base()
    other = make_pipeline("cpu", session.w, session.h, fixture_rgb)   # 对照设备固定取 CPU：两条臂都不会没 CPU
    other.set_repair_ops(session.repair_ops)
    q = lambda t: (t.clamp(0, 1) * 255).to(torch.uint8).cpu().numpy().astype(np.int16)
    diff = np.abs(q(gpu_base) - q(other.base()))
    assert diff.max() <= 1, f"重放差 {int(diff.max())} LSB：两条设备上的图层不是同一件事"
    assert len(other.repair_ops) == 2 and ops[1]["applied"] == 2


@needs_torch
def test_repair_rejects_mismatched_strokes(session):
    from lumaretouch_engine.vram import RepairOp

    with pytest.raises(ValueError, match="尺寸"):
        session.add_repair(RepairOp(op_id=1, weight=np.zeros((session.h + 4, session.w), np.uint8)))
    with pytest.raises(ValueError, match="uint8"):
        session.add_repair(RepairOp(op_id=2, weight=np.zeros((session.h, session.w), np.float32)))
    assert session.repair_ops == [], "被拒绝的操作留下了半截状态"
    assert session.repair_base is None


@needs_torch
def test_repair_resident_bytes_is_visible(session):
    """零推理与事件驱动换来的显存必须能上报：这是 M2 预算的输入。"""
    assert session.repair_resident_bytes() == 0
    session.add_repair(_op(session, 30, 30, 5))
    got = session.repair_resident_bytes()
    expect = session.repair_base.numel() * session.repair_base.element_size()
    cpu_side = sum(op.nbytes() for op in session.repair_ops)
    assert got == expect + cpu_side, f"上报 {got} != 底图 {expect} + 画笔 {cpu_side}"
    assert math.isclose(expect / (session.h * session.w * 3 * 4), 1.0, rel_tol=1e-6)


@needs_torch
def test_repair_rebuild_failure_leaves_no_trace(session, monkeypatch):
    """重建中途抛异常必须“一个字也不改”——半应用状态会产出看起来完全正常的脏帧。

    踩过的形状：先把 op append 进图层、再把 `repair_base` 置 None，异常劈在中间就留下
    三半状态：图层含新笔、底图回落 src_f32、而 `repair_version` 没变 ⇒ 下一帧的滤波
    缓存**精确命中旧底图**的结果。新底图 × 旧滤波混进同一帧，报表上一个错也看不见。
    """
    from lumaretouch_engine import vram

    session.add_repair(_op(session, 40, 40, 5, op_id=1))
    session.retouch(0.5)                         # 建好滤波缓存
    before = session.read_back().copy()
    ops_n, version = len(session.repair_ops), session.repair_version
    base_id, fkey = session.repair_base, session.filter_key
    touched = session.retouched

    def boom(*a, **kw):
        raise RuntimeError("注入的失败：裁块过大 OOM 一类")

    monkeypatch.setattr(vram, "inpaint_t", boom)
    with pytest.raises(RuntimeError, match="注入的失败"):
        session.add_repair(_op(session, 90, 20, 6, op_id=2))
    monkeypatch.undo()

    assert len(session.repair_ops) == ops_n, "失败的那笔留在了图层里"
    assert session.repair_version == version, "版本号被半推进了"
    assert session.repair_base is base_id, "底图被换掉了"
    assert session.filter_key == fkey and session.retouched is touched, "滤波缓存被动过"

    session.retouch(0.5)                          # 下一帧：必须与失败前逐字节一致
    assert np.array_equal(before, session.read_back()), "失败之后出的帧与失败前不是同一件事"
    session.add_repair(_op(session, 90, 20, 6, op_id=2))   # 同一笔重来一次应当成功
    assert len(session.repair_ops) == 2 and session.repair_base is not base_id


@needs_torch
def test_redo_stack_survives_device_replay(session, fixture_rgb):
    """换设备重放要连 redo 栈一起带：否则切一次设备就把“重做”静默抹掉。"""
    from lumaretouch_engine.vram import make_pipeline

    session.add_repair(_op(session, 60, 60, 5, op_id=1))
    session.add_repair(_op(session, session.h - 60, session.w - 60, 6, op_id=2))
    two_op_base = session.base().clone()          # “两笔”该长什么样，先拿住
    session.undo_repair()
    assert len(session.redo_ops) == 1 and len(session.repair_ops) == 1
    other = make_pipeline("cpu", session.w, session.h, fixture_rgb)
    other.set_repair_ops(session.repair_ops, session.redo_ops)
    assert len(other.redo_ops) == 1, "重放丢了 redo 栈：约束里的“撤销/重做/换设备都靠重放”没兑现"
    info = other.redo_repair()
    assert info["ops"] == 2 and info["applied"] == 2, f"重做没在新设备上复现两笔：{info}"
    q = lambda t: (t.clamp(0, 1) * 255).to(torch.uint8).cpu().numpy().astype(np.int16)
    diff = np.abs(q(two_op_base) - q(other.base()))
    assert diff.max() <= 1, f"重做后两台设备差 {int(diff.max())} LSB"


@needs_torch
def test_many_strokes_then_drag_still_zero_recompute(session):
    """拖拽期零重算不是只在“一笔”下成立：三笔叠上去之后逐帧仍不许碰滤波。"""
    for i, (cy, cx, r) in enumerate([(40, 40, 5), (60, 80, 7), (session.h - 50, 30, 6)], start=1):
        info = session.add_repair(_op(session, cy, cx, r, op_id=i))
        assert info["ops"] == i and info["applied"] == i, f"第 {i} 笔没逐笔落图：{info}"
    assert session.filter_key is None and session.retouched is None
    session.retouch(0.5)
    assert session.last_filter_ms > 0.0, "建缓存这一帧没量到滤波重算"
    for s in (0.5, 0.62, 0.8):
        session.retouch(s)
        assert session.last_filter_ms == 0.0, f"strength={s} 又重算了滤波"
    # M2-a 起键是七元组，修补版本号在最后一位（不是第 4 位了）
    assert session.filter_key[-1] == session.repair_version
    assert session.bands_key[-1] == session.repair_version, "分带键没带修补版本号"
    assert session.repair_resident_bytes() > 0, "常驻底图没被记账"


def _to_chw_u8(t):
    return (t.clamp(0.0, 1.0) * 255.0).to(torch.uint8)[0]
