"""M1-3c 拖滑块零推理：滤波结果常驻缓存的正确性。

这一节的核心主张不是"快了"，而是**快了但没有换成另一个算法**：
strength 不参与滤波，所以缓存 `retouched` 之后，混合用的表达式与操作数都跟逐帧重算
完全相同 ⇒ 输出必须**逐字节相等**，不是"≤1 LSB 容差"。一旦哪天有人把混合式改成
`img + s*(out-img)` 这种数学等价但浮点不等价的形式，这些用例就会红。

另一面是失效：缓存属于"这张源图 + 这组参数"。换图不作废就等于拿上一张脸的滤波结果
磨这张图，那比没有缓存更糟——它看起来完全正常。
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from lumaretouch_engine.face import SyntheticFace

torch = pytest.importorskip("torch")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JPG = os.path.join(HERE, "tests", "fixtures", "portrait-1024x1280.jpg")
needs_fixture = pytest.mark.skipif(not os.path.isfile(JPG),
                                   reason="缺测试人像，先跑 packaging/make-test-portrait.py")

STRENGTHS = [0.0, 0.05, 0.25, 0.37, 0.5, 0.62, 0.75, 0.9, 1.0]


def _to_u8(t):
    return (t.clamp(0.0, 1.0) * 255.0).to(torch.uint8)


@pytest.fixture
def rgb():
    from lumaretouch_engine.decode import load_rgb

    return load_rgb(JPG).rgb


@pytest.fixture
def pipe(rgb):
    from lumaretouch_engine.vram import make_pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return make_pipeline(device, rgb.shape[1], rgb.shape[0], rgb)


# ------------------------------------------------------------- 缓存 == 逐帧重算
@needs_fixture
def test_cached_mix_is_byte_identical_to_per_frame_recompute(pipe, rgb):
    """每个强度点都逐字节相等：float 层面差 0，uint8 层面差 0 LSB。

    对照物是 retouch_t（每次都重跑整条滤波链）。这两条路径给的用户承诺是"一模一样"，
    所以这里不许用容差。
    """
    from lumaretouch_engine.ops.guided import retouch_t

    for s in STRENGTHS:
        cached = pipe.retouch(s)
        fresh = retouch_t(pipe.src_f32, strength=s)
        assert torch.equal(cached, fresh), f"strength={s} 缓存路径与逐帧重算在 float 上就不等了"
        assert int((_to_u8(cached).to(torch.int16) - _to_u8(fresh).to(torch.int16)).abs().max()) == 0, \
            f"strength={s} 上屏字节不同"


@needs_fixture
def test_cached_mix_still_matches_cpu_reference(pipe, rgb):
    """上屏字节仍然落在项目既定口径内：与 numpy 参考实现差 ≤ 1 LSB。

    这里不拿 float 差当合同：CPU/GPU 的 float 差是积分图 cumsum 累加顺序噪声，
    **随宽度与 strength 增长**（实测 672 宽单趟 guided 就差 5.4e-3，s=0.85 时整条链
    差 3.2e-3），而它不是缓存引入的：同一组数据上 `pipe.retouch(s)` 与 `retouch_t(...)`
    是逐位相等（差 0.0e+00）。真正能验收的是量化后的字节，下面两条一起卡：
    最大偏差 ≤1 LSB，且不同子像素占比 <2%（不然“处处差 1”会被最大值掩盖）。
    """
    from lumaretouch_engine.ops.guided import retouch_np

    img_np = pipe.src_f32.cpu().numpy()
    for s in (0.0, 0.3, 0.85):
        got = pipe.retouch(s).cpu().numpy()
        ref = retouch_np(img_np, strength=s)
        q = lambda a: (np.clip(a, 0, 1) * 255).astype(np.uint8).astype(np.int16)
        diff = np.abs(q(got) - q(ref))
        ratio = float((diff > 0).mean())
        assert diff.max() <= 1, f"strength={s} 与 CPU 参考差 {int(diff.max())} LSB，超出验收口径"
        assert ratio < 0.02, f"strength={s} 有 {ratio:.1%} 子像素在差，1 LSB 掩盖了系统性偏差"


@needs_fixture
def test_strength_zero_is_byte_exact_through_the_cache(pipe, rgb):
    """验收口径③在缓存路径下同样成立，且必须对 mask 通道也成立。"""
    pipe.load_face(SyntheticFace()(rgb))
    for ch in (None, "skin"):
        for s in (0.0, 0):
            out = pipe.retouch(float(s), channel=ch)
            got = _to_u8(out)[0].permute(1, 2, 0).cpu().numpy().astype(np.int16)
            diff = np.abs(got - rgb.astype(np.int16))
            assert diff.max() == 0, f"channel={ch} 缓存路径下 strength=0 差了 {int(diff.max())} LSB"


# ------------------------------------------------------------------ 命中与失效
@needs_fixture
def test_first_call_filters_then_reuses(pipe, rgb):
    """第一次算滤波，之后每帧都不再算：命中缓存时 last_filter_ms 必须是 0.0。

    这条是"零推理"的全部依据；如果哪天缓存被无声绕过（键算错、张量被置空），
    这里会看到每一帧都 >0。
    """
    pipe.retouch(0.3)
    first = pipe.last_filter_ms
    assert first > 0.0, "第一帧就该把滤波算出来，否则后面测不到命中"
    for s in (0.31, 0.4, 0.5, 0.9):
        pipe.retouch(s)
        assert pipe.last_filter_ms == 0.0, f"strength={s} 又重算了一次滤波，缓存没生效"
    from lumaretouch_engine.vram import DEFAULT_DETAIL_GAIN, DEFAULT_EPS, DEFAULT_RADIUS
    # M1-4 起键多了一位：底图（修补图层）版本号。磨皮参数三元组仍须逐字对得上。
    assert pipe.filter_key[:3] == (DEFAULT_RADIUS, DEFAULT_EPS, DEFAULT_DETAIL_GAIN), \
        f"缓存键不是默认参数：{pipe.filter_key}"
    assert pipe.filter_key[3] == pipe.repair_version, f"键里第 4 位不是修补版本号：{pipe.filter_key}"
    # force 是显式重建入口，不能因为"命中"就跳过
    assert pipe.prepare(force=True) > 0.0


@needs_fixture
def test_filter_param_change_recomputes_exactly_once(pipe, rgb):
    """半径/eps/质感变了要重算，而且算完的输出要与"没有缓存时"逐字节相同。"""
    from lumaretouch_engine.ops.guided import retouch_t

    pipe.retouch(0.5)
    assert pipe.last_filter_ms > 0.0
    pipe.retouch(0.5)
    assert pipe.last_filter_ms == 0.0

    for kw in ({"radius": 20}, {"eps": 1.5e-3}, {"detail_gain": 0.6}):
        out = pipe.retouch(0.5, **kw)
        assert pipe.last_filter_ms > 0.0, f"{kw} 改了参数却没重算滤波"
        fresh = retouch_t(pipe.src_f32, strength=0.5, **kw)
        assert torch.equal(out, fresh), f"{kw} 重算后的结果与逐帧路径不等"
        # 同一组参数再拖一次：又回到零推理
        pipe.retouch(0.7, **kw)
        assert pipe.last_filter_ms == 0.0, f"{kw} 之下第二帧还在重算"


@needs_fixture
def test_new_source_image_invalidates_the_filter_cache(pipe, rgb):
    """换源图必须作废：留着旧滤波结果等于拿上一张脸磨这张图。

    这条用例故意做成"能区分新旧"的形式：换一张明显不同的图，输出必须跟着新图走。
    """
    from lumaretouch_engine.ops.guided import retouch_t

    pipe.retouch(0.5)
    assert pipe.retouched is not None
    old_out = pipe.retouch(0.5).clone()

    shifted = np.clip(rgb.astype(np.int16) + 40, 0, 255).astype(np.uint8)   # 整幅变亮
    shifted = np.ascontiguousarray(shifted)
    pipe.load_rgb_u8(shifted)
    assert pipe.retouched is None, "load_rgb_u8 没有作废滤波缓存"
    assert pipe.filter_key is None

    # 源张量本身必须已经是新图
    ref = torch.from_numpy(np.ascontiguousarray(
        (shifted.astype(np.float32) / 255.0).transpose(2, 0, 1)))[None]
    assert torch.allclose(pipe.src_f32.cpu(), ref, atol=1e-6), "源张量还不是换过的那张图"

    out = pipe.retouch(0.5)
    assert torch.equal(out, retouch_t(pipe.src_f32, strength=0.5)), "新图的结果与逐帧重算不等"
    assert not torch.equal(out, old_out), \
        "换图后输出与旧图完全一样——缓存被跨源图复用了，这在产品上是拿别人的脸磨这张图"


@needs_fixture
def test_channel_switch_reuses_the_same_filter(pipe, rgb):
    """掩膜只加权混合，不改滤波结果：换通道不该重算，也不该多存一份。

    这条同时守住显存：一张 (1,3,H,W) float32 在 672×848 上是 6.8 MB，每个通道各存一份
    会随通道数线性膨胀。
    """
    pc = SyntheticFace()(rgb)
    pipe.load_face(pc)
    pipe.retouch(0.5)                       # 全图：建缓存
    assert pipe.last_filter_ms > 0.0
    bytes_full = pipe.filter_resident_bytes()

    pipe.retouch(0.5, channel="skin")       # 换通道：只换引用
    assert pipe.last_filter_ms == 0.0, "换掩膜通道重算了滤波"
    assert pipe.filter_resident_bytes() == bytes_full, "每个通道各存了一份滤波结果"


@needs_fixture
def test_pack_does_not_mutate_the_cache(pipe, rgb):
    """pack() 里是 clamp_ 原地操作：缓存张量绝不能被它改花。

    混合返回的是新张量所以今天安全，但这条不变式很脆——哪天有人图省事让
    strength=1 直接复用 out 张量，第二帧起画面就会被永久削顶。
    """
    pipe.retouch(0.5)
    before = pipe.retouched.clone()
    for s in (0.2, 0.8, 1.0, 0.0):
        pipe.render(s)
    assert torch.equal(before, pipe.retouched), "pack/render 把缓存张量原地改写了"


@needs_fixture
def test_filter_resident_bytes_is_one_float_rgb_frame(pipe, rgb):
    """上报的常驻字节要能对上形状：这是 M2 显存预算的输入，不能是个来路不明的数。"""
    pipe.retouch(0.5)
    expect = pipe.retouched.numel() * pipe.retouched.element_size()
    assert pipe.filter_resident_bytes() == expect
    assert pipe.retouched.shape == pipe.src_f32.shape, "缓存张量与源张量不同形，多半存错了东西"


@needs_fixture
def test_cache_key_comes_from_the_normalized_params(pipe, rgb):
    """缓存键必须与真正执行的参数同源，不能一个取整一个不取整。

    坑的形状（本仓第 N 次同一类）：键里写 int(radius)、滤波却收原始 radius。传 12.5 时
    今天会响亮地崩（pad 要整数），但键与执行已经分家了——哪天 box 支持小数半径，12.5 与
    12 就会撞同一个键，下一次拿到的是错的那份且毫无症状。所以这里把"归一化后同源"钉住：
    12.5 走的就是 12 的结果，且回显的键也是 12。
    """
    from lumaretouch_engine.ops.guided import retouch_t

    a = pipe.retouch(0.5, radius=12.5)
    assert pipe.filter_key[0] == 12, f"键没归一化：{pipe.filter_key}"
    b = pipe.retouch(0.5, radius=12)
    assert pipe.last_filter_ms == 0.0, "12.5 与 12 撞了不同键，导致重复重算"
    assert torch.equal(a, b), "键说是 12，但两次结果不同——键与执行不同源"
    assert torch.equal(b, retouch_t(pipe.src_f32, strength=0.5, radius=12))


@needs_fixture
def test_illegal_filter_params_raise_at_the_lib_boundary(pipe, rgb):
    """协议层已有硬边界，库层也要有：直接调 vram 的调用方（跑靶、未来批处理）不走协议。

    eps=NaN 会让 `a = var/(var+eps)` 全片变 NaN，然后被 clamp 成 0——屏幕变成全黑而
    没有任何一条错误；负半径则会把 pad 参数变成负数。这类值不能靠调用方自觉。
    """
    for kw in ({"eps": float("nan")}, {"detail_gain": float("inf")}, {"radius": -1}):
        with pytest.raises(ValueError, match="磨皮参数非法"):
            pipe.prepare(**kw)
    # 拒绝之后缓存不能被留在半路：键与张量都还是原来的那一份
    from lumaretouch_engine.vram import DEFAULT_DETAIL_GAIN, DEFAULT_EPS, DEFAULT_RADIUS
    pipe.retouch(0.5)
    assert pipe.filter_key[:3] == (DEFAULT_RADIUS, DEFAULT_EPS, DEFAULT_DETAIL_GAIN), \
        f"非法参数把缓存状态弄乱了：{pipe.filter_key}"
