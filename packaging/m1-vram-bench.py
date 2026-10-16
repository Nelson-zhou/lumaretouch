#!/usr/bin/env python3
"""M1-2 引擎侧对拍：逐帧搬运 vs 张量常驻显存，不起 GUI。

为什么单独写一个离线脚本：跑靶矩阵里 fps 会被显示通路（每帧字节 → vsync 尾部）
干扰，1280×800 那档尤其明显。引擎侧的真实收益要在**没有显示噪声**的地方量，
再把结论带回矩阵交叉验证。

三条规矩都来自上一轮踩过的坑：
  1) 交错跑——机器漂移同时作用于两条臂，不然是比"先跑的"和"后跑的"；
  2) 看中位与最差，不挑最好看的那次；
  3) 同时验像素一致（≤2 LSB），只量速度不验对错，等于给"快但算错"开门。
     像素对拍跑 i=0 那一帧（两臂同图同系数），逐 rep 比会因指纹块位置不同而假阳。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "src"))

from lumaretouch_engine.frames import test_frame          # noqa: E402
from lumaretouch_engine.server import Engine              # noqa: E402
from lumaretouch_engine.shm import FrameShm, monotonic_ns, shm_name   # noqa: E402
from lumaretouch_engine.vram import make_pipeline         # noqa: E402

SEG_KEYS = ("synth", "pre", "filter", "kernel", "post_gpu", "cpu_post", "readback", "shm")
REPS = int(os.environ.get("REPS", "7"))
BUDGET = float(os.environ.get("LRT_RESIDENT_BUDGET_MS", "0") or 0)


def one_frame(eng: Engine, shm: FrameShm, mode: str, pipe, i: int = 0):
    """走产品同一条 _make_frame，再补上写 shm——引擎侧一帧的完整成本。"""
    pixels, seg = eng._make_frame(shm, i, mode, pipe)
    t = monotonic_ns()
    shm.write_frame(pixels)
    seg["shm"] = (monotonic_ns() - t) / 1e6
    return pixels, seg


def run_size(dev: str, w: int, h: int) -> bool:
    shm = FrameShm(shm_name(f"lrt-m1bench-{os.getpid()}-{w}"), w, h, slots=2, create=True)
    eng = Engine("m1-bench")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    ok = True
    try:
        pipe = make_pipeline(dev, w, h, test_frame(w, h, 0)[:, :, :3].copy())
        if pipe.fallback:
            print(f"  ! {pipe.fallback}")
        # 预热两条臂各自的内核与显存池
        for _ in range(6):
            one_frame(eng, shm, "pipeline_copyin", None)
            one_frame(eng, shm, "pipeline_resident", pipe)

        # 先验对错再谈快慢：同一张图、同一个系数，两条臂必须给同一份像素。
        # 只对拍 i=0 那一次：主循环里 copyin 的输入含变动的序号块、常驻臂只有系数在变，
        # 逐 rep 比会假阳性——速度测量不受影响，正确性靠下面这一次。
        a_px, _ = one_frame(eng, shm, "pipeline_copyin", None)
        b_px, _ = one_frame(eng, shm, "pipeline_resident", pipe)
        d = np.abs(a_px[:, :, :3].astype(np.int16) - b_px[:, :, :3].astype(np.int16))
        # 序号指纹块不计：copyin 是先盖章再过管线（盖章被一起滤波了），常驻是过完
        # 管线才盖章，那 16×16 本来就该不一样——这是跑靶指纹，不是算法差异
        d[16:32, 16:32] = 0
        lsb = int(d.max())
        print(f"\n== {w}x{h} · {w * h * 4 / 1e6:.2f} MB/帧 · {dev} · {REPS} 次交错 ==")
        print(f"  像素一致：两条臂最大偏差 {lsb} LSB"
              f"{'（α 恒 ' + str(int(b_px[:, :, 3].min())) + '）' if b_px[:, :, 3].min() == 255 else '（α 异常！）'}")
        if lsb > 2:
            print("  ✗ 超出 2 LSB，常驻路径算错了，速度数据不采信")
            return False

        rows: dict[str, dict] = {arm: {"total": [], **{k: [] for k in SEG_KEYS}}
                                 for arm in ("copyin", "resident")}
        for rep in range(REPS):
            for arm, mode, p in (("copyin", "pipeline_copyin", None),
                                 ("resident", "pipeline_resident", pipe)):
                t0 = monotonic_ns()
                _pixels, seg = one_frame(eng, shm, mode, p, i=rep)
                rows[arm]["total"].append((monotonic_ns() - t0) / 1e6)
                for k in SEG_KEYS:
                    rows[arm][k].append(seg.get(k, 0.0))
        med = lambda xs: statistics.median(xs)
        shown = [k for k in SEG_KEYS if any(rows[arm][k] for arm in rows)]
        print("  " + " | ".join(f"{c:>9s}" for c in ("臂", "合计", *shown)))
        for arm in ("copyin", "resident"):
            cells = [arm, f"{med(rows[arm]['total']):.2f}"] + [f"{med(rows[arm][k]):.2f}" for k in shown]
            print("  " + " | ".join(f"{str(c):>9s}" for c in cells))
        a, b = med(rows["copyin"]["total"]), med(rows["resident"]["total"])
        print(f"  合计 {a:.2f} → {b:.2f} ms/帧（Δ {b - a:+.2f}，{(b - a) / a * 100:+.0f}%）"
              f"  最差 {max(rows['copyin']['total']):.2f} → {max(rows['resident']['total']):.2f}")
        # 这条比对在 M1-3c 之前是"两臂内核应当一致"（那时常驻臂每帧也跑完整 retouch_t）。
        # 现在常驻臂拖拽期只算混合、滤波在预热阶段算一次并被缓存，两臂内核本来就该不同；
        # 还按"相等"判会把里程碑本身报成回归。换成仍然有牙齿的判据：
        #   ① 常驻臂"滤波 + 混合"不得超过 copyin 内核 —— 不许偷偷换成更贵的算法；
        #   ② 省下的量必须显著（>0.5 ms）——否则"零推理"只是没跑算法；
        #   ③ 若缓存没生效，filter 会≈整个内核，①立刻失败（这条是被绕过的检测器）。
        # 本机实测这 8 ms 的核有 ±1 ms 重复性抖动（四轮中位 7.67–8.65、min 7.67–7.83），
        # 所以阈值按抖动量级留余量，不看小数点后两位。
        ka = med(rows["copyin"]["kernel"])
        kf = med(rows["resident"]["filter"])
        kb = med(rows["resident"]["kernel"])
        same_algo = kf + kb <= ka * 1.05 + 0.2
        really_saved = ka - (kf + kb) > 0.5
        print(f"  内核 copyin {ka:.2f}（每帧全算）/ resident 滤波 {kf:.2f} + 混合 {kb:.2f}"
              f"（拖拽期）ms："
              + ("滤波已不在热路径，省下的全是真省" if same_algo and really_saved else
                 f"常驻臂单帧算法成本没降（省 {ka - (kf + kb):+.2f} ms）或反而更贵，先查代码"))
        if not (same_algo and really_saved):
            ok = False
        if BUDGET:
            ok = b <= BUDGET
            print(f"  RESIDENT_MS={b:.2f} BUDGET={BUDGET:.2f} VERDICT={'PASS' if ok else 'FAIL'}")
    finally:
        shm.close()
        shm.unlink()
    return ok


def main() -> int:
    dev = sys.argv[1] if len(sys.argv) > 1 else "cuda"
    sizes = sys.argv[2].split(",") if len(sys.argv) > 2 else ["1280x800", "960x600"]
    print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}  "
          f"name={torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'}")
    all_ok = True
    for s in sizes:
        w, h = (int(x) for x in s.lower().split("x"))
        all_ok = run_size(dev, w, h) and all_ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
