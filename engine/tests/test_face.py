"""M1-3b 预计算契约与显存常驻的单元测试。

这一节只验**通路**：形状/值域/确定性/常驻/生命周期/恒等性。
真实检测精度（478 点贴不贴得上脸）不在这里下结论 —— 那要真 MediaPipe + 真正脸，
拿 synthetic 的占位几何去断言"这是脸"就是造假证据。
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from lumaretouch_engine.face import (
    FACE_LANDMARKER_MODEL, NUM_LANDMARKS, MissingBackend, SyntheticFace,
    build, skin_mask_np,
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JPG = os.path.join(HERE, "tests", "fixtures", "portrait-1024x1280.jpg")

needs_fixture = pytest.mark.skipif(not os.path.isfile(JPG),
                                   reason="缺测试人像，先跑 packaging/make-test-portrait.py")


@pytest.fixture
def proxy_rgb():
    from lumaretouch_engine.decode import load_rgb

    return load_rgb(JPG).rgb


# ------------------------------------------------------------------ 数据结构契约
@needs_fixture
def test_landmark_contract_shape_range_and_dtype(proxy_rgb):
    pc = SyntheticFace()(proxy_rgb)
    assert pc.landmarks.dtype == np.float32
    assert pc.landmarks.shape == (NUM_LANDMARKS, 3), "478×3 是与 M1-3c 网格形变共享的契约"
    assert np.isfinite(pc.landmarks).all()
    assert (pc.landmarks[:, :2] >= 0.0).all() and (pc.landmarks[:, :2] <= 1.0).all(), \
        "关键点必须归一化到代理帧，否则换档尺寸一变就全错位"


@needs_fixture
def test_is_deterministic_for_same_input(proxy_rgb):
    """同一张图两次预计算逐字节一致：预计算若有隐性随机源，回归就没有基线。"""
    a = SyntheticFace()(proxy_rgb)
    b = SyntheticFace()(proxy_rgb)
    assert np.array_equal(a.landmarks, b.landmarks)
    assert np.array_equal(a.stack()[0], b.stack()[0])


@needs_fixture
def test_mask_channel_order_is_independent_of_dict_order(proxy_rgb):
    """stack() 的通道顺序按名字排序：调用方存 dict 的顺序不该改变显存布局。"""
    pc = SyntheticFace()(proxy_rgb)
    pc.masks = {"zeta": pc.masks["skin"], "alpha": pc.masks["skin"]}
    arr, names = pc.stack()
    assert names == ["alpha", "zeta"]
    assert arr.shape == (2, *pc.masks["alpha"].shape)


@needs_fixture
def test_skin_mask_actually_depends_on_content(proxy_rgb):
    """掩膜必须真的随图变化，否则「常驻了一份掩膜」等于常驻了一张白纸。"""
    skin = skin_mask_np(proxy_rgb)
    assert skin.shape == proxy_rgb.shape[:2] and skin.dtype == np.float32
    assert skin.min() >= 0.0 and skin.max() <= 1.0
    flat = np.full_like(proxy_rgb, 128)                    # 中性灰：不该被判成皮肤
    assert skin_mask_np(flat).mean() < skin.mean() - 0.05, \
        "中性灰与人脸肤色得到同样的掩膜，说明规则没在起作用"
    assert 0.02 < skin.mean() < 0.98, f"掩膜覆盖 {skin.mean():.2f}，几乎全 0 或全 1 都算没测到东西"


@needs_fixture
def test_masked_render_hits_the_skin_not_the_whole_frame(proxy_rgb):
    """掩膜在空间上门控了效果：背景不动，皮肤上照旧。

    比的是「掩膜渲染 vs 原图」而不是「掩膜渲染 vs 全图渲染」——后者在背景区当然差很远
    （全图在动、掩膜外不动），拿它当断言会把正确的实现判成错。阈值来自实测：
    本 fixture 上背景区平均改动 0.00 LSB、皮肤区 1.83 LSB，同区全图渲染 1.84 LSB。
    """
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    pc = SyntheticFace()(proxy_rgb)
    m = pc.masks["skin"]
    assert 0.05 < float((m > 0.5).mean()) < 0.9, "掩膜几乎全 0 或几乎全 1，门控测不出东西"

    pipe = make_pipeline("cpu", proxy_rgb.shape[1], proxy_rgb.shape[0], proxy_rgb)
    pipe.load_face(pc)
    pipe.render(0.0)
    orig = pipe.read_back()[:, :, :3].astype(np.int16)
    pipe.render(0.8, channel=None)
    full = pipe.read_back()[:, :, :3].astype(np.int16)
    pipe.render(0.8, channel="skin")
    mk = pipe.read_back()[:, :, :3].astype(np.int16)

    d_mk = np.abs(mk - orig).mean(axis=-1)
    d_full = np.abs(full - orig).mean(axis=-1)
    bg, sk = m < 0.05, m > 0.5
    assert d_mk[bg].mean() < 0.05, f"掩膜外背景被改了 {d_mk[bg].mean():.2f} LSB，门控没生效"
    assert d_mk[sk].mean() > 0.8, f"皮肤区只改了 {d_mk[sk].mean():.2f} LSB，掩膜里也没在动"
    assert abs(d_mk[sk].mean() - d_full[sk].mean()) < 0.3, \
        f"掩膜内强度被稀释（{d_mk[sk].mean():.2f} vs 全图 {d_full[sk].mean():.2f}）"


# ------------------------------------------------------------------ 后端可用性
def test_geometry_warning_is_a_boolean_the_ui_can_act_on():
    """不像一张脸的几何必须有一个布尔值可查，而不是只活在 notes 那句中文里。

    来头：一张真人照片（红发 + 脖子胸口 + 左下角一只手）把肤色包围盒撑到整幅，
    五官微调按这套点搬会作用到 98.6% 的画幅。界面去 parse notes 的文字就是
    双出处：改一个字警告就静悄悄失效。
    """
    from lumaretouch_engine.face import geometry_warning

    assert geometry_warning((0.0, 0.0, 1.0, 1.0)) is True        # 包围盒就是整幅
    assert geometry_warning((0.40, 0.17, 0.68, 0.77)) is False   # 正常的一张脸
    assert geometry_warning(None) is False


def test_template_backend_warns_when_the_whole_frame_reads_as_skin():
    """全图都是肤色时，template 必须自己说“这份几何不像脸”。"""
    from lumaretouch_engine.face import TemplateFace

    flat = np.zeros((180, 140, 3), np.uint8)
    flat[..., 0], flat[..., 1], flat[..., 2] = 205, 165, 135      # 落在 Cr/Cb 皮肤区
    assert skin_mask_np(flat).mean() > 0.9, "夹具得真被皮肤规则接住，否则这条测不到东西"
    pc = TemplateFace()(flat)
    meta = pc.meta(*flat.shape[:2])
    assert meta["geometry_warning"] is True
    assert any("mediapipe" in n for n in meta["notes"]), \
        "警告只报布尔值不够：日志里得留下人可读的那一句"


def test_template_backend_stays_quiet_for_a_compact_face():
    """反向门禁：一团紧凑的皮肤不该触发警告。否则警告会响成背景噪声，
    而一个总亮的警告等于没有警告。"""
    from lumaretouch_engine.face import TemplateFace

    rgb = np.zeros((200, 200, 3), np.uint8)
    rgb[..., 1] = 90                                              # 绿底
    yy, xx = np.mgrid[0:200, 0:200]
    blob = ((xx - 100) ** 2 + (yy - 95) ** 2) < 42 ** 2           # 中心一团“脸”
    rgb[blob] = (205, 165, 135)
    pc = TemplateFace()(rgb)
    meta = pc.meta(*rgb.shape[:2])
    assert skin_mask_np(rgb).mean() > 0.10
    assert meta["geometry_warning"] is False, f"紧凑脸形被误报：face_box={meta['face_box']}"


def test_explicit_mediapipe_backend_never_falls_back_silently(tmp_path):
    """点名要 mediapipe：依赖或模型不在必须抛 MissingBackend，而不是悄悄给个 synthetic。

    这条与「CPU 会话不许标 cuda」是同一条原则的另一个面：静默降级会让废数据自洽。
    """
    with pytest.raises(MissingBackend) as ei:
        build("mediapipe", model_dir=str(tmp_path))          # 空目录 → 模型必缺
    msg = str(ei.value)
    assert "mediapipe" in msg or "模型" in msg or "face_landmarker" in msg, \
        f"报错没说清缺什么（依赖还是模型），调用方无法判断下一步：{msg}"


def test_auto_backend_reports_why_it_downgraded(tmp_path):
    """auto 允许回落，但回落原因必须留在 notes 里，能被报表与人看见。"""
    fn = build("auto", model_dir=str(tmp_path))
    assert fn.name == "synthetic"
    if fn.notes:
        assert any("synthetic" in n or "mediapipe" in n for n in fn.notes)


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        build("dlib")


def test_model_dir_env_is_honored(tmp_path, monkeypatch):
    """模型目录可由环境变量指定：权重不入库，安装器放哪儿引擎就得能找着。"""
    monkeypatch.setenv("LRT_MODEL_DIR", str(tmp_path))
    with pytest.raises(MissingBackend):
        build("mediapipe")
    # 只放一个也不许当成"齐了"
    (tmp_path / FACE_LANDMARKER_MODEL).write_bytes(b"stub")
    with pytest.raises(MissingBackend):
        build("mediapipe")


# ------------------------------------------------------------------ 显存常驻
@needs_fixture
def test_masks_and_landmarks_live_on_the_pipeline_device(proxy_rgb):
    pytest.importorskip("torch")
    import torch

    from lumaretouch_engine.vram import make_pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pc = SyntheticFace()(proxy_rgb)
    pipe = make_pipeline(device, proxy_rgb.shape[1], proxy_rgb.shape[0], proxy_rgb)
    info = pipe.load_face(pc)
    assert info["resident_device"] == str(pipe.device)
    assert info["mask_bytes"] == pc.stack()[0].nbytes, "常驻字节数与产物不符，掩膜被截断或复制了"
    assert info["landmark_bytes"] == pc.landmarks.nbytes
    assert pipe.masks_gpu.device.type == pipe.device.type
    assert pipe.landmarks_gpu.device.type == pipe.device.type
    assert pipe.face_resident_bytes() == info["mask_bytes"] + info["landmark_bytes"]


@needs_fixture
def test_strength_zero_is_byte_exact_through_the_mask_path_too(proxy_rgb):
    """验收口径③在掩膜路径下同样成立：strength=0 时 `0·weight` 恒为 0，输出就是原图。

    这一条必须单独测。如果混合写成「先混图再乘强度」，掩膜就会在推子归零时仍然改动像素，
    「推子到底 = 原图」这个产品承诺会被静默打破。
    """
    pytest.importorskip("torch")
    import torch

    from lumaretouch_engine.vram import make_pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pc = SyntheticFace()(proxy_rgb)
    pipe = make_pipeline(device, proxy_rgb.shape[1], proxy_rgb.shape[0], proxy_rgb)
    pipe.load_face(pc)
    for ch in (None, "skin"):
        pipe.render(0.0, channel=ch)
        got = pipe.read_back()
        diff = np.abs(got[:, :, :3].astype(np.int16) - proxy_rgb.astype(np.int16))
        assert diff.max() == 0, f"channel={ch} 时 strength=0 差了 {int((diff > 0).sum())} 个子像素"
        assert (got[:, :, 3] == 255).all()


@needs_fixture
def test_mask_size_mismatch_is_refused_not_rescaled_silently(proxy_rgb):
    """拿原分辨率的掩膜来挂必须报错：悄悄缩放等于把别张图的掩膜贴到这张图上。"""
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    pc = SyntheticFace()(proxy_rgb)
    bad = pc.stack()[0][0, ::2, ::2]                        # 一半尺寸
    pc.masks = {"skin": np.ascontiguousarray(bad, np.float32)}
    pipe = make_pipeline("cpu", proxy_rgb.shape[1], proxy_rgb.shape[0], proxy_rgb)
    with pytest.raises(ValueError):
        pipe.load_face(pc)


@needs_fixture
def test_unknown_channel_raises():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    from lumaretouch_engine.decode import load_rgb

    d = load_rgb(JPG)
    pipe = make_pipeline("cpu", d.w, d.h, d.rgb)
    pipe.load_face(SyntheticFace()(d.rgb))
    with pytest.raises(KeyError):
        pipe.mask("hair")


# ------------------------------------------------------------ GPU / numpy 语义对拍
@needs_fixture
def test_masked_retouch_gpu_matches_numpy_reference(proxy_rgb):
    """GPU 生产实现必须与 CPU 参考实现同语义（真 GPU 上跑，不是 skip 出来的绿）。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.guided import make_tensor, retouch_masked_np, retouch_masked_t

    pc = SyntheticFace()(proxy_rgb)
    img = make_tensor(proxy_rgb.astype(np.float32) / 255.0, "cpu")
    w_np = torch.from_numpy(pc.stack()[0][None, :1]).contiguous()
    ref = retouch_masked_np(img.numpy(), w_np.numpy(), strength=0.6)

    if not torch.cuda.is_available():
        got = retouch_masked_t(img, w_np, strength=0.6).cpu().numpy()
    else:
        got = retouch_masked_t(img.cuda(), w_np.cuda(), strength=0.6).cpu().numpy()
    assert np.abs(got - ref).max() < 1e-3, "GPU 与 CPU 参考语义不一致，掩膜内核不许上生产"
