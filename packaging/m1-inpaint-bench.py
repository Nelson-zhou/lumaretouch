#!/usr/bin/env python3
"""M1-4 消除笔离线打靶：事件驱动省了多少、省的是不是同一件事、以及修补到底准不准。

三个问题缺一不可（沿用 m1-drag-bench 的规矩：交错跑、不挑最好看的一次、两臂都走
产品同一条通路）：

  1) **省的是不是同一件事**：cached 臂（一笔算一次，之后拖滑块只读现成底图）与
     naive 臂（每一帧都从源图重跑一遍修补）最终写进 shm 的字节必须**逐字节相等**。
     只报"事件很快"不报这个，等于给"快但换了算法"开门。
  2) **省了多少**：拖滑块期间每帧成本，以及一次事件（松手）的引擎侧成本分段
     （“把覆盖度编成行程”那一步在产品里是 **UI 侧** brush.ts 干的，另报一份，不混进预算）。
  3) **修补到底准不准**：在真图代理档上挖已知内容的洞再补回来，量孔内 MAE/PSNR——
     地面真值就是原像素，算法看不到洞内，所以这不是自证。

预算的依据写在下面，不靠"看起来合理"：
  * 一帧预算 16.7 ms（60 Hz），一次事件允许跨两帧（33 ms）再多一点余量 → 40 ms；
  * 还原精度线 8 LSB：M1-3c 定的验收口径就是"≤1 级（255）"这一量级，
    40 px 的洞能压到 8 LSB 以内意味着痘印级别（≤16 px）远好于口径。

分段归因的口径（审查后改过两处，两边都是“数字与声明对不上”的形状）：
  * 对照组每帧多付的**一整次修补重放**必须在计时窗内；先前它落在窗外，
    “×N 加速”就只量到了“作废一次滤波缓存”；
  * 事件从**空图层**起算：重放是逐笔的，叠着旧笔量出来的不是“这一笔”的成本。
"""
from __future__ import annotations

import math
import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_rgb                # noqa: E402
from lumaretouch_engine.ops.inpaint import (feather_np, hole_extent, inpaint_np,  # noqa: E402
                                            levels_for, mask_bbox, mask_from_rle,
                                            mask_to_rle)
from lumaretouch_engine.server import Engine, monotonic_ns    # noqa: E402
from lumaretouch_engine.shm import FrameShm, shm_name         # noqa: E402
from lumaretouch_engine.vram import DEFAULT_REPAIR, RepairOp, make_pipeline  # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "9"))
FRAMES = int(os.environ.get("LRT_FRAMES", "60"))
DEV = os.environ.get("LRT_DEVICE", "cuda")
RADII = [int(x) for x in os.environ.get("LRT_RADII", "4,8,16,32").split(",")]
# 一次事件（松手）的预算：帧预算 16.7 ms × 2 + 一点余量
EVENT_BUDGET_MS = float(os.environ.get("LRT_EVENT_BUDGET", "40"))
# 孔内还原精度线（LSB）
MAE_MAX = float(os.environ.get("LRT_MAE_MAX", "8.0"))
# naive/cached 的最小加速比：naive 每帧多付一整次修补 + 一次滤波重算
MIN_SPEEDUP = float(os.environ.get("LRT_MIN_SPEEDUP", "5.0"))
# 拖拽期热路径预算：与 m1-drag-bench 同一个数（纯混合）
MIX_BUDGET_MS = float(os.environ.get("LRT_MIX_BUDGET", "1.0"))
# ……但纯混合是带宽主导的，一个固定常数对 1024×1280（每帧 5.24 MB）就是错的：
# 实测斜率 ~0.27 ms/MB（三档都成立），所以预算取 `max(1.0 ms, 0.5 ms/MB × 字节)`。
# 这不是“把线画到数据外面”：0.5 ms/MB 仍是实测斜率的两倍余量，而“偷偷重跑一次滤波”
# 在产品档是 4.4 ms / 2.28 MB = 1.9 ms/MB，照样撞线。
MIX_MS_PER_MB = float(os.environ.get("LRT_MIX_MS_PER_MB", "0.5"))
# GPU(float32) 与 CPU float64 参考实现的最大允许差：沿用 M1-3a 起的验收口径（≤1 LSB）
PARITY_MAX_LSB = float(os.environ.get("LRT_PARITY_MAX", "1.0"))


def new_engine(dev: str, rgb: np.ndarray, w: int, h: int, tag: str):
    """只挂常驻会话的引擎 + 产品同一条渲染链 + 一块真 shm（与 m1-drag-bench 同构）。"""
    eng = Engine(f"m1-inpaint-{os.getpid()}-{tag}")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    pipe = make_pipeline(dev, w, h, rgb)
    eng._vram = pipe
    eng._src_rgb = rgb
    eng._image_loaded = True
    shm = FrameShm(shm_name(eng.session), w, h, slots=2, create=True)
    eng.shm = shm
    return eng, pipe, shm


def blob_u8(h: int, w: int, cy: int, cx: int, r: int) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w]
    return ((((ys - cy) ** 2 + (xs - cx) ** 2) <= r * r).astype(np.float32) * 255).astype(np.uint8)


def drag_arm(pipe, eng, op, cached: bool, frames: int):
    """一臂：拖 strength 走 frames 帧，返回每帧 ms 列表 + 最后一帧写 shm 的字节。

    cached=True 走产品通路（一笔算一次）。cached=False 是“没有事件驱动”的对照：
    每帧重新重放修补并作废滤波缓存，逼它每帧重跑——这就是 M1-4 要拿走的东西。
    两臂必须从“空图层”开始，否则同一笔会被叠加两次（重放是确定性的，叠加就不是）。
    """
    out = []
    pipe.repair_ops = []
    pipe.redo_ops = []
    pipe.repair_base = None
    pipe.drop_cache()      # M2-a 起两层都要清，见 vram.PreviewPipeline.drop_cache
    if cached:
        pipe.add_repair(op)
    last = None
    for i in range(frames):
        s = 0.25 + 0.5 * (i % 100) / 99.0
        # 计时窗口必须把对照组的“每帧重放修补”也装进去：先前它落在窗外，
        # 所谓加速比就只量到“作废一次滤波缓存”，与脚本里写的“每帧多付一整次修补”对不上。
        t0 = monotonic_ns()
        if not cached:
            pipe.set_repair_ops([op])          # 每帧重跑修补 + 作废滤波缓存
        pipe.render(s)
        eng._sync()
        shm_bytes = pipe.read_back()
        out.append((monotonic_ns() - t0) / 1e6)
        if i == frames - 1:
            last = shm_bytes.copy()
    return out, last


def event_cost(eng, pipe, weight_u8):
    """一次事件的完整成本。分段拆开是为了归因，不是为了好看：

    * `encode_ms`：把 (H,W) 覆盖度编成行程。产品里这一步在 **UI 侧**（brush.ts 同构算法），
      引擎不吃这个钱；这里用 Python 参考实现量一份，写清楚不混进引擎预算；
    * `decode_ms`：引擎侧 RLE 解码 + 羽化 + 转 uint8（产品通路真的走这一段）；
    * `repair_ms`：逐笔重放修补；`render_ms`：重算滤波 + 出帧。

    一次事件从**空图层**起算：重放是逐笔的，叠着旧笔量出来的不是“这一笔”的成本。
    """
    pipe.clear_repair(keep_redo=False)      # 清层与计时分开：不把重建空图层的开销算进事件
    t0 = monotonic_ns()
    rle = mask_to_rle(weight_u8)
    t_enc = monotonic_ns()
    hard = mask_from_rle(rle, pipe.h, pipe.w)
    soft = feather_np(hard, 2)
    w8 = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
    t_dec = monotonic_ns()
    op = RepairOp(op_id=1, weight=w8, params=dict(DEFAULT_REPAIR))
    info = pipe.add_repair(op)
    if info["ops"] != 1 or info["applied"] != 1 or not info["layer_recomputed"]:
        # 这条读的是库层字典（本层真重算了）：它不叫 cached——cmd 层会在 `**info` 之后
        # 写一条同名的 filter_cached（滤波命中缓存），两个名字共一个键就是后写吃掉先写
        raise AssertionError(f"add_repair 应当报“真重算了一笔”，实际 {info}——"
                             "这一步对不上的话后面所有分段计时都不可信")
    t_rep = monotonic_ns()
    pipe.render(0.5)
    eng._sync()
    frame = pipe.read_back()
    t_end = monotonic_ns()
    pipe.clear_repair(keep_redo=False)
    pipe.drop_cache()      # M2-a 起两层都要清，见 vram.PreviewPipeline.drop_cache
    return {"encode_ms": (t_enc - t0) / 1e6, "decode_ms": (t_dec - t_enc) / 1e6,
            "repair_ms": (t_rep - t_dec) / 1e6, "render_ms": (t_end - t_rep) / 1e6,
            "engine_ms": (t_end - t_enc) / 1e6, "total_ms": (t_end - t0) / 1e6,
            # 绑执行路径的真值：这一次出帧里滤波重算了多久（add_repair 的返回里没有这一项，
            # 把它的 repair_ms 填进 filter_ms 就是把修补当滤波报）
            "filter_ms": float(pipe.last_filter_ms),
            "rle_runs": len(rle), "frame": frame}


def hole_quality(pipe, rgb_u8, radius: int):
    """已知内容挖洞再补：走**产品通路**（add_repair → 裁块 → levels_for → DEFAULT_REPAIR），
    拿 repair_base 与原像素对拍，孔内 MAE/PSNR 就是“修补准不准”的直接证据。

    地面真值就是原像素，而算法只看得到 `img*known`（洞内为 0），所以这不是自证。
    用硬边探针（不羽化）：羽化环里的像素是“部分取填充、部分取原图”，拿原像素当
    真值去量它没有意义——环的正确性由 test_inpaint 的“笔外逐字节”那条不变式管。
    返回 (孔内 MAE, PSNR, 洞内像素, 笔外是否逐字节等于原图)：最后那条不成立意味着
    修补污染了笔外的像素，比 MAE 大更严重。
    """
    h, w = pipe.h, pipe.w
    weight = blob_u8(h, w, h // 2, w // 2, radius)
    pipe.clear_repair(keep_redo=False)
    pipe.add_repair(RepairOp(op_id=1, weight=weight, params=dict(DEFAULT_REPAIR)))
    got = (pipe.repair_base[0].clamp(0, 1) * 255).to(torch.uint8).cpu().numpy() \
        .transpose(1, 2, 0)
    inside = weight > 127
    outside = ~inside
    d = got[inside].astype(np.float64) - rgb_u8[inside].astype(np.float64)
    mae = float(np.abs(d).mean())
    mse = float((d ** 2).mean())
    psnr = 10 * math.log10(255.0 ** 2 / mse) if mse > 0 else 99.0
    return mae, psnr, int(inside.sum()), bool(np.array_equal(got[outside], rgb_u8[outside]))


def reference_parity(pipe, rgb_u8, radius: int = 8) -> float:
    """产品通路输出 vs CPU float64 参考实现在同一裁块上的最大差（LSB）。

    参考实现必须在**同一个裁块、同一组超参**上跑：产品路径是“逐笔裁块 + 层数由洞
    决定”，直接拿整幅参考去比，量到的是“裁块 vs 整幅”的分解差异，而不是两套 kernel
    与 float32/float64 的实现差异——那正是这一项要回答的问题。
    """
    p = dict(DEFAULT_REPAIR)
    h, w = pipe.h, pipe.w
    weight = blob_u8(h, w, h // 2, w // 2, radius)
    wsub_np = weight.astype(np.float32) / 255.0
    y0, y1, x0, x1 = mask_bbox(wsub_np, pad=int(p["pad"]), grow=float(p["grow"]))
    lv = levels_for(hole_extent(wsub_np), y1 - y0, x1 - x0)
    src64 = (rgb_u8.astype(np.float64) / 255.0).transpose(2, 0, 1)[None]
    ref = inpaint_np(src64[..., y0:y1, x0:x1],
                     wsub_np[None, None, y0:y1, x0:x1].astype(np.float64),
                     levels=lv, smooth_iters=int(p["smooth_iters"]),
                     refine_iters=int(p["refine_iters"]), kappa=float(p["kappa"]))
    pipe.clear_repair(keep_redo=False)
    pipe.add_repair(RepairOp(op_id=1, weight=weight, params=p))
    got = pipe.repair_base[0][:, y0:y1, x0:x1].double().cpu().numpy()
    return float(np.abs(got - ref).max()) * 255.0


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"缺 fixture：{FIXTURE}（先跑 packaging/make-test-portrait.py）")
        return 2
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("要求 cuda 但 torch.cuda.is_available()=False：离线打靶不许静默退 CPU 报好数据")
        return 2
    print(f"消除笔离线打靶 · device={DEV} reps={REPS} frames={FRAMES} "
          f"三档={BUDGETS} 源图={os.path.basename(FIXTURE)}")
    failures: list[str] = []
    rows: list[tuple] = []
    quality: list[tuple] = []
    parities: list[tuple] = []

    for budget in BUDGETS:
        one = load_rgb(FIXTURE, budget=budget)
        w, h = one.w, one.h
        # 两臂各自一个会话：同一份源图，唯一差别是"每帧重跑修补"还是"一笔一次"
        eng_a, pipe_a, shm_a = new_engine(DEV, one.rgb, w, h, f"a{budget}")
        eng_b, pipe_b, shm_b = new_engine(DEV, one.rgb, w, h, f"b{budget}")
        weight = blob_u8(h, w, h // 2, w // 2, 8)
        op_a = RepairOp(op_id=1, weight=weight, params=dict(DEFAULT_REPAIR))
        op_b = RepairOp(op_id=1, weight=weight.copy(), params=dict(DEFAULT_REPAIR))
        # 预热：torch 首次建 ROCm 上下文 + 内核模块加载要几百毫秒，混进均值会把稳态算胖
        drag_arm(pipe_a, eng_a, op_a, True, 6)
        drag_arm(pipe_b, eng_b, op_b, False, 6)
        cached_ms, cached_bytes = [], None
        naive_ms, naive_bytes = [], None
        pairs = []
        for _ in range(REPS):
            a, ab = drag_arm(pipe_a, eng_a, op_a, True, FRAMES)
            b, bb = drag_arm(pipe_b, eng_b, op_b, False, FRAMES)
            cached_ms.append(statistics.median(a))
            naive_ms.append(statistics.median(b))
            pairs.append((statistics.median(a), statistics.median(b)))
            cached_bytes, naive_bytes = ab, bb
        byte_equal = cached_bytes is not None and naive_bytes is not None and \
            bool(np.array_equal(cached_bytes, naive_bytes))
        mb_per_frame = w * h * 4 / 1e6
        mix_budget = max(MIX_BUDGET_MS, MIX_MS_PER_MB * mb_per_frame)
        speedups = [nv / cv for cv, nv in pairs]
        med_cached = statistics.median(cached_ms)
        med_naive = statistics.median(naive_ms)
        rows.append((budget, f"{w}x{h}", med_cached, med_naive, min(speedups), max(speedups),
                     byte_equal))
        if not byte_equal:
            failures.append(f"预算 {budget}：两臂 shm 字节不等——事件驱动换了算法")
        if med_cached > mix_budget:
            failures.append(f"预算 {budget}：拖拽期每帧 {med_cached:.2f} ms > {mix_budget:.2f} ms "
                            f"混合预算（{mb_per_frame:.2f} MB/帧）")
        if min(speedups) < MIN_SPEEDUP:
            failures.append(f"预算 {budget}：最小加速比 {min(speedups):.1f}× < {MIN_SPEEDUP}×")

        # 事件成本：三种笔径，9 次交错取中位（前 3 次是预热，不进统计）
        for radius in (4, 8, 16):
            wgt = blob_u8(h, w, h // 3, w // 3, radius)
            for _ in range(3):
                event_cost(eng_a, pipe_a, wgt)
            costs = [event_cost(eng_a, pipe_a, wgt) for _ in range(REPS)]
            tot = statistics.median([c["total_ms"] for c in costs])
            worst = max(c["total_ms"] for c in costs)
            eng_tot = statistics.median([c["engine_ms"] for c in costs])
            enc = statistics.median([c["encode_ms"] for c in costs])
            dec = statistics.median([c["decode_ms"] for c in costs])
            rep = statistics.median([c["repair_ms"] for c in costs])
            ren = statistics.median([c["render_ms"] for c in costs])
            runs = costs[0]["rle_runs"]
            print(f"  事件 预算={budget} r={radius:>2} 裁块行程={runs:>4}: 引擎侧 {eng_tot:6.2f} ms "
                  f"(总 {tot:6.2f} 最差 {worst:6.2f}) 编码 {enc:5.2f} | 解码 {dec:5.2f} "
                  f"/ 修补 {rep:6.2f} / 出帧 {ren:5.2f}")
            if budget == 576000 and eng_tot > EVENT_BUDGET_MS:
                failures.append(f"产品档 r={radius}：引擎侧事件 {eng_tot:.1f} ms > 预算 "
                                f"{EVENT_BUDGET_MS} ms（编码在 UI 侧，不计入）")

        # 还原精度：已知内容挖洞（走产品通路 add_repair）
        for radius in RADII:
            mae, psnr, holes, outside_ok = hole_quality(pipe_a, one.rgb, radius)
            quality.append((budget, f"{w}x{h}", radius, mae, psnr, holes, outside_ok))
            if radius <= 16 and budget == 576000 and mae > MAE_MAX:
                failures.append(f"产品档 r={radius}：孔内 MAE {mae:.2f} LSB > {MAE_MAX}")
            if not outside_ok:
                failures.append(f"预算 {budget} r={radius}：笔外像素被修补改动了（不变式 1 破）")

        # GPU(float32) vs CPU float64 参考：同一裁块、同一超参，只比实现差异
        par = reference_parity(pipe_a, one.rgb, 8)
        parities.append((budget, f"{w}x{h}", par))
        if par > PARITY_MAX_LSB:
            failures.append(f"预算 {budget}：与 float64 参考最大差 {par:.3f} LSB > {PARITY_MAX_LSB}")
        print(f"  对拍 预算={budget}: GPU float32 vs CPU float64 参考 最大 {par:.4f} LSB")

        # 对照臂（naive 会话）在同一时刻的首笔成本：只量不判。真·冷进程的首笔还要含 GPU 上下文
        # 与内核首次加载，那笔账归 m1-3a-warm 待办，不在这里下结论。
        cold = event_cost(eng_b, pipe_b, blob_u8(h, w, 40, 40, 5))
        print(f"  对照臂首笔 预算={budget}: total {cold['total_ms']:.1f} ms（只量不判，不是冷进程）")
        shm_a.close(); shm_a.unlink(); shm_b.close(); shm_b.unlink()
        eng_b._vram = None

    print("\n拖滑块热路径（ms/帧，中位）：")
    print("  预算       尺寸      cached   naive    加速比区间        字节")
    for budget, dims, cv, nv, smin, smax, eq in rows:
        print(f"  {budget:>8}  {dims:>10}  {cv:7.3f}  {nv:7.3f}  ×{smin:5.1f}–{smax:5.1f}   "
              f"{'逐字节相等' if eq else '★不等★'}")

    print("\n孔内还原精度（地面真值=原像素，算法看不到洞内）：")
    print("  预算       尺寸      洞半径  MAE(LSB)  PSNR(dB)   洞内像素  笔外逐字节")
    for budget, dims, r, mae, psnr, holes, outside_ok in quality:
        print(f"  {budget:>8}  {dims:>10}  {r:>6}   {mae:7.3f}  {psnr:7.2f}   {holes:>7}  "
              f"{'是' if outside_ok else '★被改动★'}")
    print("\n与 CPU float64 参考实现的最大差（同一裁块、同一超参）：")
    for budget, dims, par in parities:
        print(f"  {budget:>8}  {dims:>10}  {par:8.4f} LSB  （口径 ≤{PARITY_MAX_LSB}）")

    if failures:
        print("\nVERDICT=FAIL")
        for f in failures:
            print("  ✗", f)
        return 1
    print("\nVERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
