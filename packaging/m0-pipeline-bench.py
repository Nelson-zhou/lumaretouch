#!/usr/bin/env python3
"""管线归因：130 ms/帧 到底是 GPU 慢，还是我的 numpy 前后处理慢。

不起 GUI，直接把「转置 / H2D / 滤波内核 / D2H / 回写 uint8」五段分别掐表。
这一段决定 M2 的滑块架构：如果是前后处理慢，就该把张量常驻 GPU、把合成帧改成
张量生成；如果是内核慢，就得换 fp16 或降采样。
"""
from __future__ import annotations

import os
import statistics
import sys
import time

import numpy as np
import torch

sys.path.insert(0, __file__.rsplit("/packaging/", 1)[0] + "/engine/src")
from lumaretouch_engine.ops.guided import guided_t, retouch_t  # noqa: E402


def bench(fn, iters: int = 10, warmup: int = 3) -> tuple[float, float]:
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    ts = []
    for _ in range(iters):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts), max(ts)


def main() -> int:
    dev = sys.argv[1] if len(sys.argv) > 1 else "cuda"
    w, h = (int(x) for x in (sys.argv[2:4] or [1280, 800])) if len(sys.argv) > 3 else (1280, 800)
    # CI 门禁：给预算就只卡滤波内核中位耗时。M0 就是在这一段抓到回归的——
    # avg_pool2d 写法的大窗口盒式滤波要 99.7 ms，积分图只要 7.9 ms，
    # 不卡这一条，算法层换个写法就能静悄悄把帧率吃掉一个数量级。
    budget = float(os.environ.get("LRT_KERNEL_BUDGET_MS", "0") or 0)
    print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}",
          f"name={torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'}")
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    dev_t = torch.device(dev if torch.cuda.is_available() or dev == "cpu" else "cpu")

    print(f"\n== {w}x{h} 各段耗时（中位/最大，ms）==")
    a, b = bench(lambda: rgb.astype(np.float32) / 255.0)
    print(f"  uint8→float32/255          : {a:7.2f} / {b:7.2f}")
    arr = (rgb.astype(np.float32) / 255.0)
    print(f"  转置+contiguous (HWC→CHW)   : {bench(lambda: np.ascontiguousarray(arr.transpose(2, 0, 1)))[0]:7.2f}")
    cpu_t = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))[None].float()
    t = cpu_t.to(dev_t)
    print(f"  H2D 首次(含建上下文)         : {bench(lambda: cpu_t.to(dev_t), iters=3, warmup=1)[0]:7.2f}")
    for name, fn in [
        ("滤波内核 retouch_t fp32", lambda: retouch_t(t, strength=0.6)),
        ("单次 guided_t fp32", lambda: guided_t(t, 12, 6e-4)),
    ]:
        med, mx = bench(fn)
        print(f"  {name:24s}: {med:7.2f} / {mx:7.2f}")
        if budget and name.startswith("滤波内核"):
            print(f"KERNEL_MS={med:.2f} BUDGET={budget:.2f} VERDICT={'PASS' if med <= budget else 'FAIL'}")
            if med > budget:
                return 1
    with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev_t.type == "cuda"):
        med, mx = bench(lambda: retouch_t(t.half() if dev_t.type == "cuda" else t, strength=0.6))
        print(f"  {'滤波内核 fp16':24s}: {med:7.2f} / {mx:7.2f}")
    out = retouch_t(t, strength=0.6)
    print(f"  D2H (.cpu().numpy())        : {bench(lambda: out[0].detach().cpu().numpy())[0]:7.2f}")
    chw = out[0].cpu().numpy()
    print(f"  clip*255→uint8 (回写)        : {bench(lambda: (np.clip(chw, 0, 1) * 255).astype(np.uint8))[0]:7.2f}")

    # 整条端到端，跟跑靶里 pipe 那一段应当对得上
    def full():
        a2 = (rgb.astype(np.float32) / 255.0)
        tt = torch.from_numpy(np.ascontiguousarray(a2.transpose(2, 0, 1)))[None].to(dev_t)
        o = retouch_t(tt, strength=0.6)
        return (np.clip(o[0].cpu().numpy().transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
    med, mx = bench(full, iters=5)
    print(f"\n  端到端 _apply_pipeline 等价   : {med:7.2f} / {mx:7.2f}   ← 跑靶里 pipe 段应与此同量级")
    return 0


if __name__ == "__main__":
    sys.exit(main())
