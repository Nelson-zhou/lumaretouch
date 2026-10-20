"""P0 首版项②：无 GPU 必须可运行，且能力边界要如实上报（不是"代码在"就当验收通过）。

核实的现状（证据）：
- engine server 默认 self.device="cpu"；vram.PreviewPipeline 在 device 以 cuda 开头但
  torch.cuda.is_available()=False 时，如实退到 cpu 并把原因写进 pipe.fallback；
- server 会把 pipe.fallback 作为 engine_warn 事件上报（server.py 里 `if pipe.fallback: emit(...)`）。

本机有 ROCm，直接跑会走 GPU（且会把机器打满）。这里用 monkeypatch 把 torch.cuda.is_available
钉成 False 来**确定性地**模拟"无 GPU"，于是 PreviewPipeline 必然落 cpu、且张量都开在 cpu 上，
全程不碰 ROCm。这证的是三件必需的事：会退到 cpu、退得看得见、退了还能正常出帧且中性档恒等。

（真实"无 GPU 装机 + 端到端 UI + 全尺寸性能曲线"仍需在真正无 GPU 的环境里跑，属剩余工作；
本用例钉的是那条可运行路径的正确性与能力上报，不是拿它冒充完整装机验收。）
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from lumaretouch_engine.vram import make_pipeline


def _faceish(h=128, w=96):
    """一张确定性的合成"类人像"：横向渐变 + 亮度带，含非格点值，够把量化/滤波走到。"""
    y = np.linspace(40, 200, h)[:, None]
    x = np.linspace(60, 210, w)[None, :]
    base = (x + y) / 2.0
    arr = np.empty((h, w, 3), np.uint8)
    arr[..., 0] = np.clip(base, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip(base * 0.92 + 8, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip(base * 1.03 - 4, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(arr)


@pytest.fixture
def no_gpu(monkeypatch):
    """把"有没有 GPU"钉成没有：确定性地触发 CPU 退路，且张量全开在 cpu（不碰 ROCm）。"""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    yield


def test_pipeline_declared_cuda_falls_back_to_cpu_visibly(no_gpu):
    rgb = _faceish()
    h, w = rgb.shape[:2]
    p = make_pipeline("cuda:0", w, h, rgb)      # 明明要 cuda，但没有 GPU
    assert p.device.type == "cpu", "没有 GPU 却没退到 cpu：可运行路径不成立"
    assert p.fallback, "退到 cpu 却没记 fallback：能力上报会谎称 GPU 常驻"
    assert "cuda" in p.fallback and "cpu" in p.fallback


def test_cpu_render_produces_valid_frame(no_gpu):
    rgb = _faceish()
    h, w = rgb.shape[:2]
    p = make_pipeline("cpu", w, h, rgb)
    p.render(0.5)                                # 磨皮强度 0.5 在 CPU 上真跑
    frame = p.read_back()
    assert frame.shape == (h, w, 4) and frame.dtype == np.uint8
    assert np.isfinite(frame.astype(np.float32)).all()
    assert (frame[..., 3] == 255).all(), "alpha 通道没铺满：布局不符 shm 约定"


def test_cpu_strength_zero_is_byte_identical_to_source(no_gpu):
    """中性档恒等这条承诺在 CPU 上也必须成立（逐字节），否则预览与导出会差档。"""
    rgb = _faceish()
    h, w = rgb.shape[:2]
    p = make_pipeline("cpu", w, h, rgb)
    p.render(0.0)
    assert np.array_equal(p.read_back()[..., :3], rgb), "CPU 上 strength=0 不逐字节等于原图"
