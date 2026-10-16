#!/usr/bin/env python3
"""M1-3a 验收口径①「单次导入耗时」离线打靶。

为什么单独一个脚本，而不是只看跑靶日志里的 image_ready：真图导入在一场会话里只发生
一次，一次采样分不清「冷页缓存的首次代价」和「稳定态代价」——M1-1 已经因为单一采样
下错过结论（同二进制背靠背 54.1 vs 57.1 fps）。这里把三档代理预算 × N 次交错跑，
报 min 与中位，min 当"这套代码能做到的下限"，中位当"用户实际感受"。

同时它也是验收口径③的 GPU 版证据：strength=0 时 read_back 出来的 RGB 必须与解码得到的
代理图**逐字节相等**（不是近似、不是 ≤1 LSB）。这一条失败就直接非零退出，因为它一旦
破了就意味着「推子归零 = 原图」这个产品承诺是假的。

跑法（要一个带 ROCm/CUDA torch 的解释器）：
  LRT_ENGINE_PY 无关；直接 REPS=5 python3 packaging/m1-import-bench.py
"""

from __future__ import annotations

import os
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "src"))

import numpy as np                       # noqa: E402
import torch                             # noqa: E402

from lumaretouch_engine.decode import load_rgb      # noqa: E402
from lumaretouch_engine.vram import make_pipeline, warm_device   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEVICE = os.environ.get("LRT_DEVICE", "cuda")
REPS = int(os.environ.get("REPS", "5"))
# 三档代理预算：2.28 MB（M1-1 安全区）/ 2.95 MB（阈值边上）/ 5.24 MB（越线）
BUDGETS = [(576000, "576k"), (737280, "737k"), (1310720, "full")]


def one(path: str, budget: int):
    """走一遍 cmd_load_image 用的同一批调用，逐段计时。"""
    seg = {}
    d = load_rgb(path, budget)
    seg["open"] = d.t_open_ms
    seg["decode"] = d.t_decode_ms
    seg["orient"] = d.t_orient_ms
    seg["scale"] = d.t_scale_ms
    seg["decode_total"] = d.t_total_ms

    t = time.perf_counter()
    pipe = make_pipeline(DEVICE, d.w, d.h)
    if pipe.fallback:
        raise RuntimeError(f"设备回退，本组数据无效：{pipe.fallback}")
    pipe.load_rgb_u8(d.rgb)
    seg["vram_attach"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    pipe.render(0.0)
    seg["render0"] = (time.perf_counter() - t) * 1000.0
    t = time.perf_counter()
    frame = pipe.read_back()
    seg["readback"] = (time.perf_counter() - t) * 1000.0
    seg["import_total"] = seg["decode_total"] + seg["vram_attach"] + seg["render0"] + seg["readback"]

    # 逐字节保真：RGB 三区必须与解码图完全一致，alpha 恒 255
    diff = int(np.abs(frame[..., :3].astype(np.int16) - d.rgb.astype(np.int16)).max())
    alpha_ok = bool((frame[..., 3] == 255).all())
    return d, seg, diff, alpha_ok


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"✗ 缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    if DEVICE.startswith("cuda") and not torch.cuda.is_available():
        print("✗ 要求 cuda 但 torch.cuda.is_available()=False（CPU 组的数不能当 GPU 结论用）")
        return 2

    # 预热：跑的就是引擎 cmd_set_device 里那一份（同一个函数，不是另搭一个近似版）。
    # 上一版这里也“warm 一次”，但它是把 `one()` 的结果丢不要——那等于把要量的东西
    # 藏起来再报剩下的数干净。现在预热后量到的**第一张**仍然进统计，并且单独判一条：
    # 首图不得比稳态中位慢过一个比例（m1-3a-warm 的验收）。
    warm_ms = warm_device(DEVICE)
    first = one(FIXTURE, BUDGETS[0][0])

    print(f"单次导入打靶 · device={DEVICE} reps={REPS} 源图={os.path.basename(FIXTURE)}")
    print(f"预热（引擎启动时付）{warm_ms:.2f} ms；预热后的首图 {first[1]['import_total']:.2f} ms")
    print(f"{'档':>5} {'代理档':>9} {'MB/帧':>7} {'解码':>7} {'缩放':>7} "
          f"{'进显存':>7} {'首帧':>7} {'回读':>7} {'总计':>8} {'总计中位':>9} {'保真':>5}")
    rows = []
    # 交错：每轮把三档各跑一次。同档连跑会让页缓存一路变暖，档位之间就不是同一条件了
    per = {tag: [] for _, tag in BUDGETS}
    per[BUDGETS[0][1]].append(first)          # 预热后的首图就是这一档的第一个样本，不丢
    for _ in range(REPS):
        for budget, tag in BUDGETS:
            per[tag].append(one(FIXTURE, budget))
    for budget, tag in BUDGETS:
        recs = per[tag]
        d0 = recs[0][0]
        keys = ("decode", "scale", "vram_attach", "render0", "readback", "import_total")
        agg = {k: [r[1][k] for r in recs] for k in keys}
        mn, md = (min(agg["import_total"]), st.median(agg["import_total"]))
        diffs = sorted({r[2] for r in recs})
        ok = all(r[2] == 0 and r[3] for r in recs)
        print(f"{tag:>5} {f'{d0.w}x{d0.h}':>9} {d0.w * d0.h * 4 / 2**20:>7.2f}"
              f" {min(agg['decode']):>7.2f} {min(agg['scale']):>7.2f}"
              f" {min(agg['vram_attach']):>7.2f} {min(agg['render0']):>7.2f}"
              f" {min(agg['readback']):>7.2f} {mn:>8.2f} {md:>9.2f}"
              f" {'OK' if ok else 'FAIL':>5}")
        print(f"       中位：解码 {st.median(agg['decode']):.2f} · 缩放 {st.median(agg['scale']):.2f}"
              f" · 进显存 {st.median(agg['vram_attach']):.2f} · 首帧 {st.median(agg['render0']):.2f}"
              f" · 回读 {st.median(agg['readback']):.2f} · draft={d0.draft_used}")
        rows.append((tag, ok, diffs))
        if not ok:
            print(f"  ✗ 逐字节保真失败：最大偏差 {diffs} LSB")

    bad = [t for t, ok, _ in rows if not ok]
    if bad:
        print(f"✗ 非零退出：{','.join(bad)} 档 strength=0 输出与解码原图不一致")
        return 1
    print("✓ 三档 strength=0 均逐字节等于解码原图（含 alpha 恒 255）")
    # m1-3a-warm 的验收：预热之后，用户看到的**第一张**不得还是那个 ~300 ms 的冷价。
    # 判据取“稳态中位的 1.6 倍 + 20 ms”：F 轮没预热时是 299 vs 35（8.5 倍），跑过了
    # 应当贴回稳态；留 60% 余量是给页缓存与首次解码的，不是给上下文建立的。
    tag0 = BUDGETS[0][1]
    med0 = st.median([r[1]["import_total"] for r in per[tag0]])
    line = med0 * 1.6 + 20.0
    f0 = first[1]["import_total"]
    if f0 > line:
        print(f"✗ 预热后首图 {f0:.2f} ms > 判据 {line:.2f} ms（稳态中位 {med0:.2f}）："
              f"预热没盖住真实内核（warm {warm_ms:.2f} ms）")
        return 1
    print(f"✓ 预热后首图 {f0:.2f} ms ≤ {line:.2f} ms（稳态中位 {med0:.2f} ms）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
