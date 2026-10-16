#!/usr/bin/env python3
"""M1-3b 离线打靶：导入期预计算的分段成本 + 掩膜通道的逐帧代价，不起 GUI。

为什么不能在跑靶矩阵里量这几个数：矩阵里一帧的成本混着显示通路（每帧字节 →
vsync 尾部），预计算那笔又被进程级的 GPU 上下文建立盖住。要分清"每张图付一次"
和"每帧付一次"，必须在没有显示噪声的地方拆开量，再把结论带回矩阵交叉验证。

三档代理预算 × 三个数：
  1) 预计算分段：build（每进程一次）/ infer（每图一次）/ attach（每图一次 H2D）；
  2) 逐帧代价：同一张图、同一系数，全图渲染 vs 掩膜渲染交错跑，看中位也看最差；
  3) 恒等性：掩膜路径下 strength=0 必须仍与解码原图逐字节相等（验收口径③在
     M1-3b 的对偶证据——混合式一旦写成"先混图再乘强度"，这里就会红）。

规矩沿用上一轮：交错跑、不挑最好看的那次、只量速度不验对错等于给"快但算错"开门。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine import face as face_mod              # noqa: E402
from lumaretouch_engine.decode import load_rgb               # noqa: E402
from lumaretouch_engine.server import Engine, monotonic_ns   # noqa: E402
from lumaretouch_engine.shm import FrameShm, shm_name        # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
# 产品默认 576000（M1-1 字节定律定的像素预算）；另两档看成本曲线是不是线性
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "9"))
BACKEND = os.environ.get("LRT_PRECOMPUTE", "auto")
DEV = os.environ.get("LRT_DEVICE", "cuda")
# 掩膜渲染不该比全图贵：常驻多一张 (1,H,W) float32，读的带宽相对滤波核可忽略。
# 超出这个比例就不是"免费"，而是掩膜把内核换成了另一条更贵的路，必须先查代码
MASK_SLACK = float(os.environ.get("LRT_MASK_SLACK", "1.15"))


def new_engine(dev: str, rgb: np.ndarray):
    """造一个只挂了常驻会话的引擎，然后走产品同一条 _make_frame。

    不复用 _make_frame 自己拼一份近似逻辑，量出来的数就不代表产品通路。
    """
    from lumaretouch_engine.vram import make_pipeline

    eng = Engine(f"m1-pc-{os.getpid()}")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    pipe = make_pipeline(dev, rgb.shape[1], rgb.shape[0], rgb)
    eng._vram = pipe
    eng._src_rgb = rgb
    eng._image_loaded = True
    return eng, pipe


def precompute_once(eng, pipe, rgb, backend: str):
    """按 cmd_precompute 的同一拆法计三段：建图 / 推理 / 上显存。

    这里不复用 cmd_precompute，因为它要往 stdout 发事件、还要 shm；但三段的
    边界必须与它逐字一致，否则离线数与矩阵数不可比。注意产品路径是**每张图都
    重新 build 一次后端**，所以第二次调用的 build_ms 就是真实逐图成本，不是噪声。
    """
    t0 = monotonic_ns()
    fn = face_mod.build(backend)
    t1 = monotonic_ns()
    pc = fn(rgb)
    t2 = monotonic_ns()
    info = pipe.load_face(pc)
    t3 = monotonic_ns()
    eng._precompute = pc
    return pc, info, dict(
        build_ms=(t1 - t0) / 1e6, infer_ms=(t2 - t1) / 1e6,
        attach_ms=(t3 - t2) / 1e6, total_ms=(t3 - t0) / 1e6)


def run_budget(dev: str, budget: int, backend: str) -> bool:
    d = load_rgb(FIXTURE, budget=budget)
    ok = True
    print(f"\n=== 代理 {d.w}x{d.h}（{d.w * d.h} px ≤ 预算 {budget}，"
          f"{d.w * d.h * 4 / 1e6:.2f} MB/帧）· {dev} · backend={backend} ===")
    print(f"  解码 {d.t_total_ms:.2f} ms（open {d.t_open_ms:.2f} / decode {d.t_decode_ms:.2f} "
          f"/ orient {d.t_orient_ms:.2f} / scale {d.t_scale_ms:.2f}）draft_used={d.draft_used}")

    eng = pipe = None
    try:
        # 会话建立本身要计时：冷进程那笔 GPU 上下文就落在这里，不在预计算里
        t_s = monotonic_ns()
        eng, pipe = new_engine(dev, d.rgb)
        session_ms = (monotonic_ns() - t_s) / 1e6
        if pipe.fallback:
            print(f"  ! {pipe.fallback}")
        med = lambda xs: statistics.median(xs)
        print(f"  会话建立（源图 H2D + 常驻缓冲）{session_ms:.2f} ms")

        # ---- 1) 预计算分段：第一次含冷设备的 attach 与首次内核，第二次才是“每张图”的成本
        pc, info, seg1 = precompute_once(eng, pipe, d.rgb, backend)
        _pc2, info2, seg2 = precompute_once(eng, pipe, d.rgb, backend)
        print(f"  预计算 首次   build {seg1['build_ms']:.2f} + infer {seg1['infer_ms']:.2f} "
              f"+ attach {seg1['attach_ms']:.2f} = {seg1['total_ms']:.2f} ms")
        print(f"  预计算 逐图   build {seg2['build_ms']:.2f} + infer {seg2['infer_ms']:.2f} "
              f"+ attach {seg2['attach_ms']:.2f} = {seg2['total_ms']:.2f} ms")
        print(f"  产物    {pc.backend} · {info['mask_channels']} · {pc.landmarks.shape} "
              f"关键点 · 掩膜常驻 {info['mask_bytes'] / 1e6:.3f} MB"
              f"（帧缓冲的 {info['mask_bytes'] / (d.w * d.h * 4) * 100:.1f}%）"
              f"，关键点 {info['landmark_bytes']} B")
        if info["mask_bytes"] != pc.stack()[0].nbytes or info2["mask_bytes"] != info["mask_bytes"]:
            print("  ✗ 常驻字节与 CPU 原件不等量，H2D 被截断，速度数据不采信")
            return False

        # ---- 2) 恒等性先过关：算错了再快也没意义
        for ch in (None, pc.stack()[1][0]):
            pipe.render(0.0, channel=ch)
            got = pipe.read_back()
            diff = np.abs(got[:, :, :3].astype(np.int16) - d.rgb.astype(np.int16))
            bad = int((diff > 0).sum())
            print(f"  strength=0 channel={ch or '全图'}：最大 {int(diff.max())} LSB，"
                  f"非零子像素 {bad}")
            if diff.max() != 0 or not (got[:, :, 3] == 255).all():
                print("  ✗ 掩膜路径破坏了「推子到底 = 原图」，口径③不成立")
                ok = False

        # ---- 3) 逐帧代价：全图 vs 掩膜，走产品同一条 _make_frame，交错跑
        shm = FrameShm(shm_name(f"lrt-pc-{os.getpid()}-{d.w}"), d.w, d.h, slots=2, create=True)
        channel = pc.stack()[1][0]
        eng._precompute = pc
        try:
            arms = ("full", "masked")
            for arm in arms:                       # 预热两条臂的内核
                eng._channel = None if arm == "full" else channel
                for _ in range(4):
                    eng._make_frame(shm, 0, "image_stream", pipe)
            rows = {a: {"total": [], "kernel": []} for a in arms}
            for rep in range(REPS):
                for arm in arms:                   # 同一 rep 内交错，机器漂移同时作用于两臂
                    eng._channel = None if arm == "full" else channel
                    t = monotonic_ns()
                    _px, seg = eng._make_frame(shm, rep, "image_stream", pipe)
                    rows[arm]["total"].append((monotonic_ns() - t) / 1e6)
                    rows[arm]["kernel"].append(seg["kernel"])
        finally:
            shm.close()
            shm.unlink()
        print(f"  逐帧（{REPS} 次交错，image_stream 同一条 _make_frame）")
        for arm in arms:
            r = rows[arm]
            print(f"    {arm:>7s}  中位 {med(r['total']):.2f}  最差 {max(r['total']):.2f} ms"
                  f"   内核中位 {med(r['kernel']):.2f}（min {min(r['kernel']):.2f}）")
        a, b = med(rows["full"]["total"]), med(rows["masked"]["total"])
        ratio = b / a if a else float("inf")
        print(f"  掩膜相对全图：{a:.2f} → {b:.2f} ms/帧（×{ratio:.2f}，Δ {b - a:+.2f}）")
        if ratio > MASK_SLACK:
            print(f"  ✗ 超过 {MASK_SLACK:.2f}× 容差：通道渲染不是「只换张量引用」，"
                  f"多半是 _make_frame 没把 channel 传下去")
            ok = False
        # 内核段两条臂跑的是同一个 guided filter，只差一个逐像素乘法。对不上就说明
        # 分段不可信——与 m1-vram-bench 同一条自检
        ka, kb = med(rows["full"]["kernel"]), med(rows["masked"]["kernel"])
        if abs(ka - kb) > max(1.0, 0.2 * ka):
            print(f"  ! 内核中位差 {ka:.2f} vs {kb:.2f} ms 偏大，分段先别拿来下结论")
    finally:
        if pipe is not None:
            pipe.clear_face()
            del pipe
    return ok


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像：{FIXTURE}（先跑 packaging/make-test-portrait.py）")
        return 2
    print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}  "
          f"name={torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'}")
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("要求 cuda 但没有 GPU：这一轮没有意义，直接退出（不给假的绿）")
        return 2
    all_ok = True
    for b in BUDGETS:
        all_ok = run_budget(DEV, b, BACKEND) and all_ok
    print(f"\nVERDICT={'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
