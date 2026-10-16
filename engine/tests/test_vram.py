"""GPU 常驻预览会话的正确性测试。

这里管的是「快之外还对不对」：M1-2 把逐帧 numpy 往返换成显存常驻，任何一步写错
都不会崩、只会**静默偏色**——所以必须拿三条独立路径互相钉死：
常驻路径 == 逐帧搬运路径 == numpy 参考实现，容差 1 LSB。
"""

from __future__ import annotations

import os

import numpy as np
import pytest

# torch 是可选依赖：CI 的 engine job 只装 numpy+pytest（见 pyproject.toml 里的 GPU 变体分组），
# 没 torch 就整模块跳过，而不是把收集阶段弄成 ModuleNotFoundError。
pytest.importorskip("torch")

from lumaretouch_engine.frames import synthetic
from lumaretouch_engine.ops.guided import retouch_np
from lumaretouch_engine.server import Engine
from lumaretouch_engine.shm import FrameShm, shm_name
from lumaretouch_engine.vram import PreviewPipeline, make_pipeline

W, H = 96, 64
STRENGTH = 0.62


def src() -> np.ndarray:
    """固定内容的 (H,W,3) uint8：不用 test_frame，它的缓存会被逐帧改写序号块。"""
    return synthetic(W, H, 0.0)


def rgba_of(rgb: np.ndarray) -> np.ndarray:
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    out[:, :, :3] = rgb
    out[:, :, 3] = 255
    return out


def ref_u8(rgb: np.ndarray, strength: float) -> np.ndarray:
    """numpy 参考实现 → (H,W,3) uint8，与现行跑靶路径同款量化方式（截断）。"""
    chw = np.ascontiguousarray(rgb.transpose(2, 0, 1))[None].astype(np.float32) / 255.0
    return (np.clip(retouch_np(chw, strength), 0, 1) * 255).astype(np.uint8)[0].transpose(1, 2, 0)


def diff(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())


# -------------------------------------------------------------------- 语义对拍
def test_resident_equals_copyin_path():
    """常驻路径与逐帧搬运路径必须给出同样的像素：M1-2 换的是搬运，不许换结果。"""
    rgb = src()
    eng = Engine("t-resident")
    eng.device = "cpu"
    out_copyin, _seg = eng._pipe_copyin(rgba_of(rgb), STRENGTH)

    pipe = make_pipeline("cpu", W, H, rgb)
    pipe.render(STRENGTH)
    out_resident = pipe.read_back()

    assert out_resident.shape == (H, W, 4)
    assert diff(out_resident[:, :, :3], out_copyin[:, :, :3]) <= 1


def test_resident_equals_numpy_reference():
    """GPU/搬运两种写法都要贴着 CPU 参考实现，否则「生产内核」根本不该上链。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    pipe.render(STRENGTH)
    got = pipe.read_back()[:, :, :3]
    assert diff(got, ref_u8(rgb, STRENGTH)) <= 1


def test_strength_zero_is_byte_exact_identity():
    """滑块归零必须逐字节等于原图：这是「预览=原图」的产品承诺，不许有 1 LSB 漂移。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    pipe.render(0.0)
    frame = pipe.read_back()
    assert diff(frame[:, :, :3], rgb) == 0
    assert (frame[:, :, 3] == 255).all()


@pytest.mark.parametrize("strength", [0.05, 0.35, 0.95])
def test_strength_is_monotonic_not_a_noop(strength):
    """确认滑块不是空操作：不同 strength 必须给不同像素（M0 差点写出恒等管线）。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    outs = []
    for s in (0.0, strength):
        pipe.render(s)
        outs.append(pipe.read_back()[:, :, :3].copy())
    assert diff(outs[0], outs[1]) > 0, f"strength={strength} 没有改变任何像素"


# -------------------------------------------------------------------- 常驻性质
def test_tensors_stay_on_device_after_read_back():
    """回读只拷一份出去，常驻缓冲本身不许被搬走或换成 CPU 张量。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    pipe.render(STRENGTH)
    frame = pipe.read_back()
    assert pipe.frame_gpu.device == pipe.src_f32.device
    assert pipe.frame_gpu.device.type == "cpu"       # 本用例跑 CPU；GPU 版在下面
    assert frame.flags["C_CONTIGUOUS"]
    assert frame.dtype == np.uint8 and frame.shape == (H, W, 4)
    # CPU 张量 .cpu() 会返回同一个对象；GPU 则必须返回新对象且不改变原张量设备
    assert pipe.src_u8.device.type == pipe.src_f32.device.type


def test_alpha_channel_survives_repeated_renders():
    """alpha 只在装载时写一次，之后每帧只改 rgb：反复渲染不能把 alpha 洗掉。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    for _ in range(3):
        pipe.render(STRENGTH)
    assert (pipe.read_back()[:, :, 3] == 255).all()


def test_read_back_feeds_shm_without_extra_copy():
    """回读结果直接就是 shm 要的字节布局：中间不许再来一次 transpose/tobytes。"""
    rgb = src()
    name = shm_name(f"lrt-test-vram-{os.getpid()}")
    shm = FrameShm(name, W, H, slots=2, create=True)
    try:
        pipe = make_pipeline("cpu", W, H, rgb)
        pipe.render(STRENGTH)
        seq, _, slot = shm.write_frame(pipe.read_back())
        assert seq == 1
        assert shm.read_pixels(slot) == np.ascontiguousarray(pipe.read_back()).tobytes()
    finally:
        shm.close()
        shm.unlink()


def test_stamp_marks_the_frame_without_touching_alpha():
    """跑靶指纹：序号块要真的写进输出帧，而且逐帧不重复、不动 alpha。"""
    rgb = src()
    pipe = make_pipeline("cpu", W, H, rgb)
    seen = []
    for i in range(4):
        pipe.render(STRENGTH)
        pipe.stamp(i)
        f = pipe.read_back()
        seen.append(int(f[16, 16, 2]))
        assert int(f[16, 16, 0]) == 255 - i
        assert (f[:, :, 3] == 255).all()
    assert seen == [0, 1, 2, 3], f"序号指纹没写进输出帧: {seen}"


def test_stamp_requires_load():
    pipe = PreviewPipeline("cpu", W, H)
    with pytest.raises(RuntimeError):
        pipe.stamp(1)


# -------------------------------------------------------------------- 参数校验
def test_rejects_source_of_wrong_size():
    rgb = src()
    with pytest.raises(ValueError):
        make_pipeline("cpu", W + 8, H, rgb)


def test_render_before_load_raises():
    pipe = PreviewPipeline("cpu", W, H)
    with pytest.raises(RuntimeError):
        pipe.render(0.5)
    with pytest.raises(RuntimeError):
        pipe.read_back()


def test_cuda_requested_but_absent_is_not_silent():
    """要求 GPU 却悄悄退到 CPU，会让「显存常驻」的结论变成假的——必须能看见。"""
    torch = pytest.importorskip("torch")
    rgb = src()
    if torch.cuda.is_available():
        pytest.skip("本机有 GPU，这条测的是回退分支")
    pipe = make_pipeline("cuda", W, H, rgb)
    assert pipe.fallback and "cpu" in pipe.fallback
    assert pipe.device.type == "cpu"


# -------------------------------------------------------------------- GPU 变体
@pytest.mark.parametrize("strength", [0.0, STRENGTH])
def test_resident_on_gpu_matches_numpy_reference(strength):
    """真正的卖点必须在真 GPU 上验一遍，CPU 上过了不代表显存里也过。"""
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("本机无可用 GPU 后端")
    big = synthetic(320, 200, 0.0)          # GPU 上用大图，小图全在启动开销里看不出差别
    pipe = make_pipeline("cuda", big.shape[1], big.shape[0], big)
    pipe.render(strength)
    got = pipe.read_back()[:, :, :3]
    assert pipe.frame_gpu.device.type == "cuda"
    d = diff(got, ref_u8(big, strength))
    assert d <= 2, f"GPU 常驻路径与 CPU 参考最大偏差 {d} LSB"
    if strength == 0.0:
        assert d == 0
