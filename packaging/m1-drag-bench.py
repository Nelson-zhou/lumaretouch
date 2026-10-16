#!/usr/bin/env python3
"""M1-3c 离线打靶：拖滑块零推理省下多少、以及省的是不是"同一件事"，不起 GUI。

G 轮把 58.8 fps 的缺口归因到逐帧滤波那 4.9 ms 吃掉了 vsync 余量。这一节的主张是
把它从热路径里拿走，所以必须回答两个问题，缺一不可：

  1) 省了多少：逐帧重算 vs 缓存混合，同一张图、同一系数序列，看中位也看最差；
  2) 省的是不是同一件事：两条臂最终写进 shm 的字节必须**逐字节相等**。
     只报速度不报这个，等于给"快但换了算法"开门——而这里恰恰有一次这样的诱惑：
     把混合式改写成 `img + s*(out-img)` 也能很快、数学上也等价，但浮点上不再相等。

规矩沿用前两轮：交错跑（同一次打靶里两臂交替，避免机器热漂移单边占便宜）、
不挑最好看的那次、两臂都走产品同一条 `Engine._make_frame`——唯一的差别是在重算臂
里每次调用前把缓存清掉。自己拼一份近似逻辑，量出来的就不代表产品通路。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_rgb               # noqa: E402
from lumaretouch_engine.face import SyntheticFace            # noqa: E402
from lumaretouch_engine.server import Engine, monotonic_ns   # noqa: E402
from lumaretouch_engine.shm import FrameShm, shm_name        # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "9"))
FRAMES = int(os.environ.get("LRT_FRAMES", "60"))
DEV = os.environ.get("LRT_DEVICE", "cuda")
# 一次纯混合的预算：读一张 float RGB + 写一张，带宽主导。超过这个数就说明缓存被绕过了。
MIX_BUDGET_MS = float(os.environ.get("LRT_MIX_BUDGET", "1.0"))
# 至少应有的加速比。逐帧重算在产品档是 ~4.5 ms、纯混合 ~0.1 ms，5× 是极保守的下界。
MIN_SPEEDUP = float(os.environ.get("LRT_MIN_SPEEDUP", "5.0"))
# 本机单次测量的噪声底（G 轮实测 fps ±3、内核 ±0.05 ms 量级）；小于它不算差异
NOISE_MS = float(os.environ.get("LRT_NOISE_MS", "0.05"))
# 拖强度（零推理）时的峰值显存应当不高于建缓存后的这个倍数。拖半径是另一回事：
# 它每帧重算，重算期间旧缓存与新滤波中间量共存，峰值必然抬升——那条只量不判，
# 是给 M2（质感/半径滑块）的预算输入，不是本节的门禁。
CHURN_PEAK_RATIO = float(os.environ.get("LRT_CHURN_PEAK_RATIO", "5.0"))


def new_engine(dev: str, rgb: np.ndarray, w: int, h: int, tag: str):
    """只挂常驻会话的引擎 + 产品同一条 _make_frame + 一块真 shm。"""
    from lumaretouch_engine.vram import make_pipeline

    eng = Engine(f"m1-drag-{os.getpid()}-{tag}")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    pipe = make_pipeline(dev, w, h, rgb)
    eng._vram = pipe
    eng._src_rgb = rgb
    eng._image_loaded = True
    name = shm_name(f"lrt-drag-{os.getpid()}-{tag}-{w}x{h}")
    shm = FrameShm(name, w, h, slots=2, create=True)
    return eng, pipe, shm


def drop_cache(pipe):
    """把滤波缓存清空：下一次 _make_frame 就会走 M1-3b 的每帧重算路径。

    这是两臂唯一的差别。不清缓存也不允许——那样两臂量到的是同一条路，差值恒为 0，
    "省了多少"就变成一个自证的空话。
    """
    pipe.retouched = None
    pipe.filter_key = None


def run_arm(eng, pipe, shm, recompute: bool, frames: int):
    """跑一段帧，返回 (每帧内核 ms 列表, 每帧引擎总 ms 列表, 最后一帧字节, 重算次数)。"""
    kernels, totals, last, refilter = [], [], None, 0
    for i in range(frames):
        if recompute:
            drop_cache(pipe)
        t0 = monotonic_ns()
        pixels, seg = eng._make_frame(shm, i, "image_stream", pipe)
        eng._sync()
        totals.append((monotonic_ns() - t0) / 1e6)
        # 重算臂的滤波与混合都算"内核"；缓存臂的 filter 恒 0，kernel 只剩混合
        kernels.append(seg["filter"] + seg["kernel"])
        if seg["filter"] > 0:
            refilter += 1
        last = pixels.copy()
        if recompute and seg["filter"] <= 0:
            raise SystemExit(f"重算臂第 {i} 帧没重算滤波（filter={seg['filter']}）——两臂在量同一条路")
    return kernels, totals, last, refilter


def main() -> int:
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("无 GPU：这份打靶量的是 ROCm 内核，退出码 2，不给假绿")
        return 2
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2

    failures: list[str] = []
    print(f"设备={DEV}  重复={REPS}  每次帧数={FRAMES}  混合预算={MIX_BUDGET_MS} ms  "
          f"最低加速={MIN_SPEEDUP}x\n")
    for budget in BUDGETS:
        d = load_rgb(FIXTURE, budget=budget)
        rgb = d.rgb
        print(f"── 代理档 {d.w}x{d.h}（{budget} px，{(d.w * d.h * 4) / 1e6:.2f} MB/帧）")
        eng, pipe, shm = new_engine(DEV, rgb, d.w, d.h, "main")
        try:
            pipe.load_face(SyntheticFace()(rgb))
            for tag, channel in (("全图", None), ("掩膜 skin", "skin")):
                # 不是引擎的模式，而是先选上通道再跑同一条 image_stream
                eng._channel = channel
                cached_k, cached_t, bytes_c = [], [], None
                recompute_k, recompute_t, bytes_r = [], [], None
                refilter_max = 0
                for _ in range(REPS):                      # 交错：同一轮里两臂交替
                    k, t, b, _n = run_arm(eng, pipe, shm, True, FRAMES)
                    recompute_k.append(statistics.median(k))
                    recompute_t.append(statistics.median(t))
                    bytes_r = b
                    k, t, b, n = run_arm(eng, pipe, shm, False, FRAMES)
                    cached_k.append(statistics.median(k))
                    cached_t.append(statistics.median(t))
                    bytes_c = b
                    refilter_max = max(refilter_max, n)

                med = lambda xs: statistics.median(xs)
                worst = lambda xs: max(xs)
                speedup = med(recompute_k) / max(med(cached_k), 1e-9)
                # 配对差：逐次相减再看中位，比两堆中位直接相减更抗机器热漂移
                pair = [a - b for a, b in zip(recompute_k, cached_k)]
                saved = med(pair)
                beats_noise = sum(1 for x in pair if x > NOISE_MS)

                print(f"   {tag}：逐帧重算内核 {med(recompute_k):.2f}（最差 {worst(recompute_k):.2f}）"
                      f" ms → 缓存混合 {med(cached_k):.3f}（最差 {worst(cached_k):.3f}） ms"
                      f"   {speedup:.1f}x")
                print(f"     配对节省中位 {saved:.2f} ms/帧，{beats_noise}/{REPS} 次超过噪声底 "
                      f"{NOISE_MS} ms；整帧引擎耗时 {med(recompute_t):.2f} → {med(cached_t):.2f} ms；"
                      f"缓存臂重算次数（最差一次）{refilter_max}/{FRAMES}")

                if refilter_max > 1:
                    failures.append(f"{d.w}x{d.h} {tag}：缓存臂 {FRAMES} 帧里重算了 {refilter_max} 次"
                                    f"（最多只允许第一帧那一次）")
                if med(cached_k) > MIX_BUDGET_MS:
                    failures.append(f"{d.w}x{d.h} {tag}：纯混合 {med(cached_k):.3f} ms 超预算 "
                                    f"{MIX_BUDGET_MS} ms")
                if speedup < MIN_SPEEDUP:
                    failures.append(f"{d.w}x{d.h} {tag}：加速只有 {speedup:.1f}x，低于 {MIN_SPEEDUP}x")
                if beats_noise < REPS:
                    failures.append(f"{d.w}x{d.h} {tag}：{REPS - beats_noise}/{REPS} 次节省没超过噪声底，"
                                    f"省下来的量不可信")
                # 最重要的一条：快，但算的是同一件事
                if bytes_c is None or bytes_r is None or not np.array_equal(bytes_c, bytes_r):
                    diff = 0 if None in (bytes_c, bytes_r) else int(np.abs(
                        bytes_c.astype(np.int16) - bytes_r.astype(np.int16)).max())
                    failures.append(f"{d.w}x{d.h} {tag}：缓存臂与重算臂的上屏字节不同（最大 {diff} LSB）")
                else:
                    print("     字节对拍：两臂最终 shm 载荷逐字节相等 ✓")
        finally:
            shm.close()
            try:
                os.unlink(f"/dev/shm/{shm_name(f'lrt-drag-{os.getpid()}-main-{d.w}x{d.h}')}")
            except FileNotFoundError:
                pass

        # 恒等性：缓存路径下 strength=0 仍必须逐字节等于解码原图（验收口径③）
        eng2, pipe2, shm2 = new_engine(DEV, rgb, d.w, d.h, "id")
        try:
            pipe2.prepare()                       # 先把缓存建起来，再验零强度
            for ch in (None, "skin"):
                if ch == "skin":
                    pipe2.load_face(SyntheticFace()(rgb))
                out = pipe2.retouch(0.0, channel=ch)
                pipe2.pack(out)
                got = pipe2.read_back()
                dd = np.abs(got[:, :, :3].astype(np.int16) - rgb.astype(np.int16))
                if int(dd.max()) != 0:
                    failures.append(f"{d.w}x{d.h} channel={ch}：缓存路径下 strength=0 差 "
                                    f"{int(dd.max())} LSB")
            print(f"   strength=0 恒等：全图与掩膜通道均 0 LSB ✓")
        finally:
            shm2.close()
            try:
                os.unlink(f"/dev/shm/{shm_name(f'lrt-drag-{os.getpid()}-id-{d.w}x{d.h}')}")
            except FileNotFoundError:
                pass

        # 成本侧：零推理不是白拿的，多常驻一张 float RGB；而拖半径仍旧每帧重算。
        # 这两个数分开量，M2 才知道"把半径滑块也做成免重算"值多少钱。
        eng3, pipe3, shm3 = new_engine(DEV, rgb, d.w, d.h, "mem")
        try:
            base = torch.cuda.memory_allocated()
            MiB = lambda x: x / 1024 / 1024
            pipe3.retouch(0.5)                       # 建缓存
            after_prepare = MiB(torch.cuda.memory_allocated() - base)
            if pipe3.filter_resident_bytes() != d.w * d.h * 3 * 4:
                failures.append(f"{d.w}x{d.h}：滤波常驻 {pipe3.filter_resident_bytes()} B"
                                f" != w*h*3*4={d.w * d.h * 3 * 4} B")

            def settle(fn, n=200):
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                for i in range(n):
                    fn(i)
                torch.cuda.synchronize()
                return MiB(torch.cuda.max_memory_allocated() - base)

            peak_steady = settle(lambda i: pipe3.pack(pipe3.retouch(0.2 + 0.6 * (i % 100) / 99.0)))
            peak_churn = settle(lambda i: pipe3.pack(pipe3.retouch(0.5, radius=12 if i % 2 else 20)))
            print(f"   显存：建缓存后常驻 {after_prepare:.1f} MiB（含滤波 "
                  f"{pipe3.filter_resident_bytes() / 1e6:.2f} MB）；拖强度峰值 "
                  f"{peak_steady:.1f} MiB，拖半径（每帧重算）峰值 {peak_churn:.1f} MiB"
                  f"，比 ×{peak_churn / max(peak_steady, 0.01):.1f}")
            if peak_steady > after_prepare * CHURN_PEAK_RATIO:
                failures.append(f"{d.w}x{d.h}：拖强度时峰值 {peak_steady:.1f} MiB 远大于常驻 "
                                f"{after_prepare:.1f} MiB，缓存可能在累积而不是替换")
        finally:
            shm3.close()
            try:
                os.unlink(f"/dev/shm/{shm_name(f'lrt-drag-{os.getpid()}-mem-{d.w}x{d.h}')}")
            except FileNotFoundError:
                pass

    print()
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print("\nVERDICT=FAIL")
        return 1
    print("VERDICT=PASS  （零推理省下的确实全是滤波，且一帧字节都没变）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
