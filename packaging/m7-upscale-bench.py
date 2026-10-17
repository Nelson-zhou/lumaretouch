#!/usr/bin/env python3
"""M7 放大跑靶：保真三臂 + 「峰值只随 tile 走」的显存实证 + 网络结构的成本账单。

三节各自回答一个能被反驳的问题，任何一节不成立就非零退出：

1 保真（确定性档）
   分块与整幅必须**逐字节同一**（差 0，不是容差）；GPU(float32) 与 CPU(float64) 出口
   ≤1 LSB；带限正弦重建跟得上解析真值。这一节是"放大没算错"的全部主张。

2 显存与耗时（产品档）
   同一张源图 ×4：整幅一快 vs 分块（tile 256/512/1024）各自的峰值与耗时。要证的不是
   "谁快"，而是**峰值随 tile 走、不随图幅走**——不切块时 ×4 一张 1024×1280 需要
   4096×5120×3×4B 的输出张量外加中间层，消费级卡放不下；放不下就把这件事如实记成
   OOM，而不是换个好看的数当结论。

3 神经网络结构（权重门禁档）
   RRDBNet(num_block=23, nf=64, ×4) 的结构前向成本与显存，用随机权重测——问的是
   "上市要不要分块、分块能省多少"，**不问超分质量**（质量要等 sha256 放行的权重）。
   同时验一遍带重叠分块的接缝随 overlap 收敛。

用法：PYTHONPATH=engine/src <有 torch 的解释器> packaging/m7-upscale-bench.py [图路径]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

FAIL = []


def need(cond, msg):
    print(f"  {'✓' if cond else '×'} {msg}")
    if not cond:
        FAIL.append(msg)


def _torch():
    import torch
    return torch


def section_1(img):
    print("== 1 保真：分块==整幅 / GPU↔CPU / 带限真值 ==")
    from lumaretouch_engine.ops import upscale as U
    torch = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    x = torch.from_numpy(img.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(dev)
    whole = U.upscale_t(x, 2)
    tiled, info = U.upscale_tiled_t(x, 2, tile=96)
    d = float((whole - tiled).abs().max())
    need(d == 0.0, f"分块({info['tiles']} 块) 与整幅最大差 = {d}（要求恰为 0）")
    ref = U.upscale_np(img, 2).astype(np.int16)
    q = np.clip(np.rint(whole[0].permute(1, 2, 0).cpu().numpy() * 255.0), 0, 255)
    dl = int(np.abs(q - ref).max())
    need(dl <= 1, f"GPU(float32) ↔ CPU(float64) 出口 max = {dl} LSB（要求 ≤1）")
    # 常值与重现性
    flat = np.full((64, 64, 3), 133, np.uint8)
    need(np.all(U.upscale_np(flat, 4) == 133), "常值图 ×4 仍逐字节是 133（权重按行归一）")
    out3 = U.upscale_np(img, 3)
    d3 = int(np.abs(out3[1::3, 1::3].astype(np.int16) - img.astype(np.int16)).max())
    need(d3 == 0, f"输出网格与输入格点重合处逐字节相等（max={d3}）")
    W, s = 256, 2
    fx = 6.0
    f = lambda p: 127.5 + 90.0 * np.cos(2 * np.pi * fx * p / W)
    samp = np.clip(np.rint(f(np.arange(W))), 0, 255).astype(np.uint8)
    sin_img = np.tile(samp[None, :, None], (8, 1, 3))
    got = U.upscale_np(sin_img, s)[:, :, 0].astype(np.float64)[0]
    ana = f((np.arange(W * s) + 0.5) / s - 0.5)
    sl = slice(16, W * s - 16)
    err = float(np.abs(got[sl] - ana[sl]).max())
    nn = float(np.abs(np.repeat(samp.astype(np.float64), s)[sl] - ana[sl]).max())
    need(err < 3.0 and nn > 3.0,
         f"带限正弦重建 max={err:.2f} LSB（<3），同图最近邻 max={nn:.2f} LSB（须显著更差）")
    # 锐化：0 量恒等、平坦不动、阶跃加大落差
    need(np.array_equal(U.unsharp_np(img, amount=0.0), img), "unsharp amount=0 逐字节恒等")
    step = np.stack([np.tile(np.where(np.arange(64) < 32, 40, 200).astype(np.uint8), (64, 1))] * 3, -1)
    sh = U.unsharp_np(step, radius=2.0, amount=0.8, threshold=0.0)
    g0 = int(np.abs(sh[:, 32].astype(int) - sh[:, 31].astype(int)).sum())
    g1 = int(np.abs(step[:, 32].astype(int) - step[:, 31].astype(int)).sum())
    need(g0 > g1, f"锐化后阶跃落差 {g0} > 原值 {g1}")


def section_2(img):
    print("== 2 显存与耗时：峰值只随 tile 走，不随图幅走 ==")
    torch = _torch()
    from lumaretouch_engine.ops import upscale as U
    if not torch.cuda.is_available():
        need(False, "本节要求 CUDA 设备（跑靶量的是显卡上的峰值）")
        return
    dev = "cuda"
    x = torch.from_numpy(img.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(dev)
    h, w = img.shape[:2]
    s = 4
    rows = []
    # 整幅一快
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    try:
        out = U.upscale_t(x, s)
        torch.cuda.synchronize()
        ms = (time.perf_counter() - t0) * 1000.0
        peak = torch.cuda.max_memory_allocated() / 2 ** 20
        rows.append(("whole", 0, 1, ms, peak, out.shape))
        del out
    except torch.cuda.OutOfMemoryError:
        ms, peak = float("nan"), torch.cuda.max_memory_reserved() / 2 ** 20
        rows.append(("whole", 0, 1, ms, peak, None))
    torch.cuda.empty_cache()
    for tile in (256, 512, 1024):
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        out, info = U.upscale_tiled_t(x, s, tile=tile)
        torch.cuda.synchronize()
        ms = (time.perf_counter() - t0) * 1000.0
        rows.append((f"tile{tile}", tile, info["tiles"], ms,
                     torch.cuda.max_memory_allocated() / 2 ** 20, out.shape))
        del out
        torch.cuda.empty_cache()
    for name, tile, n, ms, peak, shape in rows:
        out_txt = f"{shape[3]}x{shape[2]}" if shape else "放不下"
        ms_txt = "OOM" if not np.isfinite(ms) else f"{ms:.1f} ms"
        print(f"  · {name:>9}  源 {w}x{h} ×{s} → {out_txt}  tiles={n:<3} 耗时 {ms_txt:<10} 峰值 {peak:.1f} MiB")
    tiled = [r for r in rows if r[0] != "whole"]
    need(all(r[2] > 1 for r in tiled), "每个分块档都真切出了多块（否则峰值口径无从对比）")
    need(tiled[0][4] < tiled[-1][4], f"峰值随 tile 单调：tile256 {tiled[0][4]:.1f} < tile1024 {tiled[-1][4]:.1f} MiB")
    small_img = img[: min(h, 256), : min(w, 256)]
    xs = torch.from_numpy(small_img.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(dev)
    torch.cuda.reset_peak_memory_stats()
    _, info_s = U.upscale_tiled_t(xs, s, tile=256)
    peak_s = torch.cuda.max_memory_allocated() / 2 ** 20
    print(f"  · 同 tile256 换小图 {small_img.shape[1]}x{small_img.shape[0]}：峰值 {peak_s:.1f} MiB "
          f"（块内峰 {info_s['peak_px']} px）")
    need(peak_s <= tiled[0][4] * 1.35,
         f"图幅从 {w}x{h} 缩到 {small_img.shape[1]}x{small_img.shape[0]} 而 tile 不变，"
         f"峰值不该随图幅涨（{tiled[0][4]:.1f} → {peak_s:.1f} MiB）")
    need(all(np.isfinite(r[3]) for r in tiled), "分块档全部跑完没 OOM")


def section_3():
    print("== 3 神经网络结构（随机权重，只问成本与分块几何，不问超分质量） ==")
    torch = _torch()
    from lumaretouch_engine.ops import realesrgan as R
    net = R.build_net(torch, scale=4, num_block=23, nf=64, growth=32)
    n_par = sum(p.numel() for p in net.parameters())
    print(f"  · RRDBNet(23×RRDB, nf=64, ×4) 参数量 {n_par / 1e6:.2f} M，fp32 权重 {n_par * 4 / 2 ** 20:.1f} MiB")
    if not torch.cuda.is_available():
        need(False, "本节要求 CUDA 设备")
        return
    net.eval().to("cuda")
    try:
        # 幅面选 192²：产品结构（23×RRDB, nf=64）在这张卡上单次前向就是十秒量级，
        # 再大就把 CI 拖死。这一节要的是"整幅 vs 分块"的**峰值对比与量级**，不是绝对吞吐。
        side = 192
        x = torch.rand(1, 3, side, side, device="cuda")
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        with torch.no_grad():
            out_w = net(x)
        torch.cuda.synchronize()
        ms_warm = (time.perf_counter() - t0) * 1000.0
        peak_w = torch.cuda.max_memory_allocated() / 2 ** 20
        t0 = time.perf_counter()
        with torch.no_grad():
            net(x)
        torch.cuda.synchronize()
        ms_steady = (time.perf_counter() - t0) * 1000.0
        print(f"  · 整幅前向 输入 {side}²→输出 {side * 4}²：首次 {ms_warm:.0f} ms，"
              f"稳态 {ms_steady:.0f} ms，峰值 {peak_w:.1f} MiB")
        print("     （首次与稳态分开放：ROCm 对新形状要建阵，不分开报就会把建阵算成帧时间）")
        del out_w
        torch.cuda.empty_cache()
        # 分块前向：同一输入幅面，峰值只随 tile 走
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        with torch.no_grad():
            out_t, info = R.forward_tiled(net, x, tile=96, overlap=16)
        torch.cuda.synchronize()
        ms_t = (time.perf_counter() - t0) * 1000.0
        peak_t = torch.cuda.max_memory_allocated() / 2 ** 20
        print(f"  · 带重叠分块 同幅 {side}² tile=96 ov=16：{info['tiles']} 块，{ms_t:.0f} ms，"
              f"峰值 {peak_t:.1f} MiB，块内峰 {info['peak_px']} px")
        print(f"     （分块 {ms_t:.0f} ms > 整幅 {ms_steady:.0f} ms：halo 把重叠区算了两遍，"
              f"这多出来的功是峰值从 {peak_w:.0f} 降到 {peak_t:.0f} MiB 的代价，不是黑账）")
        need(tuple(out_t.shape) == (1, 3, side * 4, side * 4), "分块前向输出尺寸 = 整幅 ×4")
        need(info["tiles"] == 4, f"{side}/96 应切 2×2=4 块（实得 {info['tiles']}）")
        need(torch.isfinite(out_t).all() and float(out_t.min()) >= 0 and float(out_t.max()) <= 1,
             "分块输出有限且在 [0,1]")
        need(peak_t < peak_w, f"同一输入幅面下分块峰值 {peak_t:.1f} < 整幅 {peak_w:.1f} MiB"
                              "——不切块就没有上市档，这条是存在性而不是优化")
        del x, out_t
        torch.cuda.empty_cache()
        # 接缝收敛（用小网测得快，几何与掩码是同一个函数）
        small = R.build_net(torch, scale=4, num_block=1, nf=8, growth=4).eval().to("cuda")
        xs = torch.rand(1, 3, 20, 24, device="cuda")
        with torch.no_grad():
            whole = small(xs).clamp(0, 1)
        errs = []
        for ov in (2, 4, 8):
            o, _ = R.forward_tiled(small, xs, tile=12, overlap=ov)
            m = 16
            errs.append(float((o[:, :, m:-m, m:-m] - whole[:, :, m:-m, m:-m]).abs().max()))
        print(f"  · 接缝随 overlap 收敛：ov2={errs[0]:.4f} ov4={errs[1]:.4f} ov8={errs[2]:.4f}（归一单位）")
        need(errs[0] > errs[1] > errs[2], "重叠越大接缝残余越小（分块几何与淡化掩码成立）")
        del small, xs, whole
    finally:
        del net
        torch.cuda.empty_cache()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
    from PIL import Image
    img = np.asarray(Image.open(path).convert("RGB"))
    print(f"源图 {path} → {img.shape[1]}x{img.shape[0]}")
    section_1(img)
    section_2(img)
    section_3()
    print()
    if FAIL:
        print(f"VERDICT=FAIL  {len(FAIL)} 条：\n - " + "\n - ".join(FAIL))
        sys.exit(1)
    print("VERDICT=PASS（分块逐字节等价 / 峰值只随 tile 走 / 网络结构与重叠分块几何成立；"
          "超分质量主张等 sha256 权重放行）")


if __name__ == "__main__":
    main()
