#!/usr/bin/env python3
"""M6 抠图/换底跑靶：确定性合成的保真与耗时 + 色键分离度 + BiRefNet 结构成本账。

三条判据都是能独立证伪的数：
1. **合成 CPU↔GPU 逐像素 ≤1 LSB**（同一串式子的两个实现），并测产品档单帧合成耗时；
2. **线性光证据**：白叠黑 50% 必须落在线性域（≈188），不是 sRGB 平均（128）；
3. **色键**在影楼纯色底合成卡上把背景/前景分对（背景区 alpha→0、前景区→1）。
BiRefNet 结构：不上权重也量一次 1024 前向的耗时与峰值显存（证明管线能扛住这个负载形态），
但**不报任何抠图质量指标**——没权重就没质量主张，这条与 lama 同规。

判据行写 VERDICT=PASS/FAIL；非零退出即破。跑法（臂需 GPU，无 GPU 则合成对拍用 CPU 参考自洽）：
  LRT_DEVICE=cuda python packaging/m6-bg-bench.py
"""
from __future__ import annotations

import os
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "src"))

import numpy as np  # noqa: E402

from lumaretouch_engine.ops import matting as M  # noqa: E402

DEVICE = os.environ.get("LRT_DEVICE", "cuda")
PROXY = (848, 672)          # (h,w) 产品代理档
REPS = int(os.environ.get("REPS", "20"))


def _device_or_none():
    try:
        import torch
        if DEVICE.startswith("cuda") and torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return None


def bench_composite_parity(dev):
    rng = np.random.default_rng(0)
    fg = rng.integers(0, 256, size=(PROXY[0], PROXY[1], 3), dtype=np.uint8)
    alpha = (rng.random(PROXY) * 255).astype(np.uint8)
    bg = np.array([20, 60, 200], np.uint8)
    ref = M.composite_np(fg, alpha, bg).astype(np.int16)
    t_ref = _ms(lambda: M.composite_np(fg, alpha, bg), REPS)
    if dev is None:
        return None, t_ref
    import torch
    fgt = torch.from_numpy(fg.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(dev)
    at = torch.from_numpy(alpha.astype(np.float32) / 255.0)[None, None].to(dev)
    bgt = torch.from_numpy(bg.astype(np.float32) / 255.0).to(dev)

    def one():
        return M.composite_quantize_t(M.composite_t(fgt, at, bgt))[0].permute(1, 2, 0).cpu().numpy().astype(np.int16)

    got = one()
    maxlsb = int(np.abs(got - ref).max())
    t_gpu = _ms(one, REPS)
    return maxlsb, (t_ref, t_gpu)


def bench_linear_light():
    fg = np.full((4, 4, 3), 255, np.uint8)
    bg = np.zeros((4, 4, 3), np.uint8)
    alpha = np.full((4, 4), 128, np.uint8)
    return int(M.composite_np(fg, alpha, bg)[0, 0, 0])


def bench_key():
    img = np.zeros((200, 200, 3), np.float64)
    img[:, :] = [0.1, 0.2, 0.9]
    img[60:140, 60:140] = [0.9, 0.4, 0.05]
    img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    a = M.key_matte_np(img)
    return float(a[60:140, 60:140].mean()), float(np.concatenate([a[:20, :20].ravel(), a[-20:, -20:].ravel()]).mean())


def bench_birefnet(dev):
    """BiRefNet 结构在 1024 档的前向耗时与峰值显存（不上权重，纯负载形态取证）。"""
    try:
        import torch
    except Exception:
        return None
    if dev is None:
        return None
    from lumaretouch_engine.ops import birefnet as B
    net = B.build_net(torch, base=48).eval().to(dev)
    x = torch.zeros(1, 3, 1024, 1024, device=dev)
    with torch.no_grad():
        net(x)
        if dev == "cuda":
            torch.cuda.synchronize()
        base_mem = torch.cuda.memory_allocated() if dev == "cuda" else 0
        ts = []
        for _ in range(5):
            t0 = time.perf_counter()
            net(x)
            if dev == "cuda":
                torch.cuda.synchronize()
            ts.append((time.perf_counter() - t0) * 1000)
            torch.cuda.reset_peak_memory_stats() if dev == "cuda" else None
        net(x)
        if dev == "cuda":
            torch.cuda.synchronize()
        peak = (torch.cuda.max_memory_allocated() - base_mem) / 2 ** 20 if dev == "cuda" else 0
    return min(ts), st.median(ts), peak


def _ms(fn, reps):
    fn()                                   # warm
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return st.median(ts)


def main() -> int:
    dev = _device_or_none()
    print(f"M6 换底跑靶 · device={dev or 'CPU-only'} reps={REPS} 档={PROXY[1]}×{PROXY[0]}")
    fails = []

    maxlsb, timing = bench_composite_parity(dev)
    if dev is None:
        print(f"[合成耗时 CPU] 中位 {timing:.1f} ms（无 GPU，臂跳过对拍）")
    else:
        t_ref, t_gpu = timing
        print(f"[合成 CPU↔GPU] max={maxlsb} LSB · 耗时 CPU {t_ref:.1f} / GPU {t_gpu:.1f} ms")
        if maxlsb > 1:
            fails.append(f"GPU 与 CPU 参考差 {maxlsb} LSB（应 ≤1）")

    mid = bench_linear_light()
    print(f"[线性光证据] 白叠黑 50% = {mid}（线性域应≈188，sRGB 平均会得 128）")
    if not 175 <= mid <= 205:
        fails.append(f"合成没走线性光：半透明混出 {mid}（偏离 188）")

    fga, bga = bench_key()
    print(f"[色键] 前景均值={fga:.3f}（应→1） 背景均值={bga:.3f}（应→0）")
    if fga < 0.9 or bga > 0.1:
        fails.append("色键在纯色底上没把前景/背景分对")

    br = bench_birefnet(dev)
    if br is None:
        print("[BiRefNet 结构] 跳过：无 GPU（质量本就不在无权重时主张）")
    else:
        mn, md, peak = br
        print(f"[BiRefNet 结构] 1024² 前向 中位 {md:.1f}/min {mn:.1f} ms · 峰值额外 {peak:.0f} MiB"
              "（仅负载取证，不报抠图质量）")

    if fails:
        print("VERDICT=FAIL  " + " ; ".join(fails))
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
