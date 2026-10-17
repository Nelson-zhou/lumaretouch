#!/usr/bin/env python3
"""M2-b 离线打靶：478 点 TPS 五官微调到底动没动对地方、快没快在对地方，不起 GUI。

主张有两句，缺一句都不算成立：

  1) **它动的是"该动的那几个点"，而且只动那一块。** 四件事各自要有一个数：
     · 恒等：三个滑块全零 ⇒ 上屏逐字节等于"没建这一层"。这不是废话——形变盖在
       磨皮与修容之后，任何一次"顺手重采样"都会让 strength=0 那条承诺碎掉。
     · 紧支撑：窗外像素逐字节不动。瘦脸不许把背景拖走。
     · 控制点精度：场在控制点处等于请求值（<2% 峰值）。窗半径写错时这里会红，
       而"画面有没有变"永远不红。
     · 纯轴：只请求 y 位移时 x 分量必须**精确为 0**。affine 项转置写反时这条红、
       上面那条还绿（误差被摊到两个分量上了）。
  2) **快，而且算的是同一件事。** "缩放单位场"与"每帧重解一次 TPS"两条臂的上屏
     字节必须逐字节相等；拖滑块期间 deform_builds 一分不增。

臂之间交替跑，避免机器热漂移单边占便宜；口径沿用 m1-drag-bench / m2-dnb-bench。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine import face                                # noqa: E402
from lumaretouch_engine.decode import load_rgb                     # noqa: E402
from lumaretouch_engine.ops.deform import (                        # noqa: E402
    CHIN_PEAK_OF_FACE_H, EYE_PEAK_OF_IRIS, KINDS, SLIM_PEAK_OF_FACE_W,
    controls, face_frame, identity_grid, support_radii, tps_field_np,
    tps_field_t, unit_field, warp_np, warp_t)
from lumaretouch_engine.quant import quantize_t                    # noqa: E402
from lumaretouch_engine.server import monotonic_ns                 # noqa: E402
from lumaretouch_engine.vram import make_pipeline                  # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "5"))
FRAMES = int(os.environ.get("LRT_FRAMES", "40"))
DEV = os.environ.get("LRT_DEVICE", "cuda")
OUT_DIR = os.path.join(HERE, "..", "build", "m2-face")

# ---- 判据（全是实测量纲）----
CTRL_TOL = 0.02          # 控制点位移误差 ÷ 请求峰值
MIX_BUDGET_MS = 1.0      # 拖磨皮滑块的每帧既定线，M2-b 不许把它弄退化
# 形变段的预算按每 MB 给：grid_sample 与“零位移保留”那两步都是逐像素的，
# 一个与尺寸无关的常数预算会在小档上恒真、在大档上恒假（上一版就是这么写的）。
# 实测：0.60 MB 上 0.52 ms、1.71 MB 上 1.08 ms、3.93 MB 上 2.99 ms → ≈ 0.8 ms/MB。
DEFORM_BUDGET_MS = 0.8   # 小档下限
DEFORM_MS_PER_MB = 1.3   # 每 MB 源图的形变段预算（留了 60% 余量）
MIN_DEFORM_SPEEDUP = 8.0  # 每帧重解 TPS ÷ 缩放单位场 的最低加速比
CPU_REF_TOL = 1e-3       # GPU float64→float32 与 CPU float64 参考的场差（px）
PEAK_TOL = 0.02          # 峰值位移与设计比例的相对容差


def _proxy(budget: int):
    """按像素预算解出代理档，并给出这张图的脸形关键点。"""
    d = load_rgb(FIXTURE, budget=budget)
    rgb = d.rgb
    pc = face.build("template")(rgb)
    return rgb, pc


def _bytes_of(pipe, strength: float) -> np.ndarray:
    pipe.render(strength)
    return pipe.read_back()[..., :3].copy()


# ============================================================ 1 保真与作用面
def _wide_target(rgb: np.ndarray) -> np.ndarray:
    """把人物缩到 55% 贴到一张高对比网格画布上，造出一块“真的在支撑窗外的背景”。

    为什么需要它：测试人像这张图脸占满整个代理档，模板拟合出的支撑圆（1.6R）把
    整幅全盖住了——“窗外逐字节不动”在那种靶上量不到东西（n_out 恒为 0，判据退化）。
    上一版 1b 就是这么“绿”的。背景用棋盘 + 竖横条纹：一旦被拖走就是 LSB 级的大改动。
    """
    h, w = rgb.shape[:2]
    ch, cw = int(h * 1.9), int(w * 1.9)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.int32)
    canvas = np.where(((xx // 24 + yy // 24) % 2)[..., None].astype(bool),
                      np.array((246, 8, 208), np.uint8), np.array((8, 232, 24), np.uint8))
    small = np.ascontiguousarray(rgb[:int(h * 0.55) // 2 * 2, :int(w * 0.55) // 2 * 2])
    sh, sw = small.shape[:2]
    y0, x0 = (ch - sh) // 2, (cw - sw) // 2
    canvas[y0:y0 + sh, x0:x0 + sw] = small
    return np.ascontiguousarray(canvas)


def part_fidelity(failures: list[str]) -> None:
    print("\n=== 1) 保真与作用面（真图，逐档）")
    for budget in BUDGETS:
        rgb, pc = _proxy(budget)
        h, w = rgb.shape[:2]
        pipe = make_pipeline(DEV, w, h, rgb)
        pipe.prepare()
        base = _bytes_of(pipe, 0.5)
        info = pipe.build_deform(pc.landmarks)
        lm = pc.landmarks
        cx, cy, R, fw, fh = face_frame(lm, h, w)
        r0, r1 = support_radii(R)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        outside = np.hypot(xx - cx, yy - cy) >= r1

        # 1a 建了单但全零 ⇒ 逐字节等于没建
        pipe.set_deform_amounts({k: 0.0 for k in KINDS})
        zero = _bytes_of(pipe, 0.5)
        if not np.array_equal(zero, base):
            failures.append(f"{w}x{h} 1a 全零滑块仍改了画面（差 {int(np.abs(zero.astype(int) - base.astype(int)).max())} LSB）")

        # 1b 逐 kind：窗外逐字节不动 + 控制点精度 + 纯轴
        if int(outside.sum()) == 0:
            print(f"  {w}x{h} 注意：脸占满代理档，支撑圆盖住整幅 ⇒ 本档的窗外判据是空的，"
                  f"另用缩图贴网格画布的靶量（见 1b'）")
        for kind in KINDS:
            pipe.set_deform_amounts({k: (0.0 if k != kind else 1.0) for k in KINDS})
            got = _bytes_of(pipe, 0.5)
            d = np.abs(got.astype(np.int32) - base.astype(np.int32)).max(axis=2)
            n_out = int((d[outside] > 0).sum())
            changed = float((d > 0).mean())
            P, D, meta = controls(lm, kind, 1.0, h, w)
            n = len(P) - 8
            f64 = tps_field_np(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0)
            req = D[:n]
            peak = float(np.abs(req).max())
            # 在**精确坐标**处取场值，不拿 round() 取整像素："TPS 在控制点处等于请求值"
            # 是亚像素位置上的解析性质，整像素取点最多带 0.5 px 的位置误差。big_eye
            # 满档峰值才 7.5 px、容差 0.02·peak = 0.15 px，取点误差能吃掉 89% 的预算——
            # 于是判据过不过取决于关键点落在哪个像素附近，而不是实现对不对。
            err = float(np.abs(_sample_bilinear(f64, P[:n, 0], P[:n, 1]) - req).max())
            print(f"  {w}x{h} {kind:10s} 峰值 {peak:6.2f} px  控制点误差 {err:.4f} px"
                  f"  改动像素 {changed:6.1%}  窗外改动 {n_out} px")
            if n_out:
                failures.append(f"{w}x{h} 1b {kind} 窗外有 {n_out} px 被拖走")
            if err > CTRL_TOL * peak:
                failures.append(f"{w}x{h} 1b {kind} 控制点误差 {err:.3f} > {CTRL_TOL}·峰值")
            if changed < 0.002:
                failures.append(f"{w}x{h} 1b {kind} 几乎没改到画面，这条判据退化了")
            # 1c 峰值位移必须落在设计比例上（换档、换构图才不变形）
            want = {"slim_face": SLIM_PEAK_OF_FACE_W * fw,
                    "big_eye": EYE_PEAK_OF_IRIS * _iris_r(lm, h, w),
                    "small_chin": CHIN_PEAK_OF_FACE_H * fh}[kind]
            if abs(peak - want) > PEAK_TOL * want:
                failures.append(f"{w}x{h} 1c {kind} 峰值 {peak:.2f} 偏离设计比例 {want:.2f}")

        # 1b' 同一组控制点打到“背景真的在窗外”的靶上：窗外必须逐字节不动
        wide = _wide_target(rgb)
        wh, ww = wide.shape[:2]
        wpc = face.build("template")(wide)
        wpipe = make_pipeline(DEV, ww, wh, wide)
        wpipe.prepare()
        wbase = _bytes_of(wpipe, 0.5)
        wpipe.build_deform(wpc.landmarks)
        wcx, wcy, wR, wfw, wfh = face_frame(wpc.landmarks, wh, ww)
        _wr0, wr1 = support_radii(wR)
        wyy, wxx = np.mgrid[0:wh, 0:ww].astype(np.float64)
        wout = np.hypot(wxx - wcx, wyy - wcy) >= wr1
        worst = 0
        if int(wout.sum()) == 0:
            failures.append(f"{w}x{h} 1b' 背景靶仍没有窗外像素，这条判据是恒真的——"
                            "要么放大画布要么收紧支撑")
        for kind in KINDS:
            wpipe.set_deform_amounts({k: (1.0 if k == kind else 0.0) for k in KINDS})
            wd = np.abs(_bytes_of(wpipe, 0.5).astype(np.int32) - wbase.astype(np.int32)).max(axis=2)
            worst = max(worst, int(wd[wout].max()) if int(wout.sum()) else -1)
        print(f"  {w}x{h} 1b' 背景靶 {ww}x{wh}：窗外 {wout.mean():.1%} 像素，"
              f"三臂最大改动 {worst} LSB")
        if worst != 0:
            failures.append(f"{w}x{h} 1b' 背景靶上窗外被拖走（最大 {worst} LSB）")
        del wpipe

        # 1d 纯轴：只请求 y 位移时 x 分量精确为 0
        P, D, meta = controls(lm, "small_chin", 1.0, h, w)
        assert np.abs(D[:, 0]).max() == 0.0, "small_chin 不该有 x 请求"
        f = tps_field_np(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0)
        if float(np.abs(f[..., 0]).max()) != 0.0:
            failures.append(f"{w}x{h} 1d 纯 y 请求冒出 {float(np.abs(f[..., 0]).max()):.4f} px 的 x 位移")

        # 1e GPU 与 CPU 参考同阶
        gt = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), h, w,
                         cx=cx, cy=cy, R=r1, r0=r0, device=DEV).cpu().numpy()
        dev = float(np.abs(gt - f.astype(np.float32)).max())
        print(f"  {w}x{h} GPU−CPU 场最大 {dev:.3e} px")
        if dev > CPU_REF_TOL:
            failures.append(f"{w}x{h} 1e GPU 与 CPU 参考差 {dev:.4f} px")
        del pipe
    print("  （1a–1e 全绿才算“动对了地方”）")


def _iris_r(lm, h, w) -> float:
    from lumaretouch_engine.ops.deform import IRIS_LEFT, IRIS_RIM_LEFT
    c = lm[IRIS_LEFT, :2] * [w, h]
    return float(np.mean([np.hypot(*(lm[q, :2] * [w, h] - c)) for q in IRIS_RIM_LEFT]))


# ============================================================ 2 常驻 vs 重算
def part_parity(failures: list[str]) -> None:
    """缩放单位场与每帧重解 TPS 必须是**同一件事**（逐字节），否则"零推理"是偷来的。"""
    print("\n=== 2) 常驻缩放 vs 每帧重解 TPS 的字节对拍")
    for budget in BUDGETS:
        rgb, pc = _proxy(budget)
        h, w = rgb.shape[:2]
        pipe = make_pipeline(DEV, w, h, rgb)
        pipe.prepare()
        pipe.build_deform(pc.landmarks)
        amounts = {"slim_face": 0.62, "big_eye": 0.31, "small_chin": 0.44}
        # 重算臂的入参必须是**没形变**的混合结果。拿 retouch(0.5) 当入参会把它
        # 已经过完形变的输出再 warp 一次（上一版就是这么错的，量出 237 LSB 的假矛盾）。
        pipe.set_deform_amounts({k: 0.0 for k in KINDS})
        pre = pipe.retouch(0.5).cpu().numpy()
        pipe.set_deform_amounts(dict(amounts))
        resident = _bytes_of(pipe, 0.5)
        cx, cy, R, _fw, _fh = face_frame(pc.landmarks, h, w)
        r0, r1 = support_radii(R)
        acc = None
        for kind, a in amounts.items():
            P, D, _m = controls(pc.landmarks, kind, a, h, w)
            f = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), h, w,
                            cx=cx, cy=cy, R=r1, r0=r0, device=DEV)
            acc = f if acc is None else acc + f
        naive = warp_np(pre, acc.cpu().numpy()[None], 1.0)
        naive_u8 = quantize_t(torch.from_numpy(naive))[0].permute(1, 2, 0).cpu().numpy()
        dd = np.abs(naive_u8.astype(np.int32) - resident.astype(np.int32)).max(axis=2)
        print(f"  {w}x{h} 常驻 vs 重算：最大 {int(dd.max())} LSB，"
              f"有差异像素 {int((dd > 0).sum())}（{(dd > 0).mean():.4%}）")
        if dd.max() > 1:
            failures.append(f"{w}x{h} 缩放单位场与重解 TPS 差 {int(dd.max())} LSB（>1 就不是同一件事）")
        if (dd > 0).mean() > 0.02:
            failures.append(f"{w}x{h} 两条臂有 {(dd > 0).mean():.2%} 像素不一致，"
                            "不只是量化边界的事")
        del pipe


# ============================================================ 3 性能
def part_speed(failures: list[str]) -> None:
    print(f"\n=== 3) 每帧成本（{REPS} 次交替 × {FRAMES} 帧）")
    for budget in BUDGETS:
        rgb, pc = _proxy(budget)
        h, w = rgb.shape[:2]
        mb = h * w * 3 / 1e6
        resident, recompute, off = [], [], []
        for rep in range(REPS):
            # 交替顺序：每轮换一次先后，机器热漂移就不会单边占便宜。
            # 但**身份必须跟着结果走**：上一版先 `seq = [seq[1], seq[0], seq[2]]` 再
            # `res, rec, non = seq[0](), seq[1](), seq[2]()`，奇数轮里 seq[0] 是重解臂，
            # 于是“常驻”那堆混进了重解样本、“每帧重解”那堆混进了常驻样本。REPS=5 时
            # 正确那份占多数，中位数仍落在它上面（只是偏向三份正确样本里最慢的一个，
            # 所以本表历次报的 33–41× 与实际 33.6–41.3× 对得上）——但这是一个只在
            # “奇数次重复 + 两臂差距悬殊”两个巧合下才成立的正确：重复数取偶数，或两臂
            # 差距降到噪声量级（m3-color 的常驻/重传就是 0.2 ms 那一档），两堆会直接
            # 被读成同一件事。本轮在 m3-color 里它把判据推到 0.200 贴闸红，当场被
            # 上传计数抓包，这里一并把形状改对。
            def make(on):
                return lambda: _time_arm(rgb, pc.landmarks, on, h, w)

            order = [True, False, None] if rep % 2 == 0 else [False, True, None]
            got = {key: make(key)() for key in order}
            resident.append(got[True])
            recompute.append(got[False])
            off.append(got[None])
        r_tot = statistics.median([a[0] for a in resident])
        r_seg = statistics.median([a[1] for a in resident])
        c_tot = statistics.median([a[0] for a in recompute])
        n_tot = statistics.median([a[0] for a in off])
        builds = max(a[2] for a in resident)
        vram = max(a[3] for a in resident)
        print(f"  {w}x{h}（{mb:.2f} MB）  不开形变 {n_tot:6.3f}  常驻 {r_tot:6.3f}"
              f"（其中形变段 {r_seg:5.3f}）  每帧重解 {c_tot:7.3f}"
              f"  加速 {c_tot / max(r_tot, 1e-6):5.1f}×")
        if builds != 0:
            failures.append(f"{w}x{h} 常驻臂拖滑块期间解了 {builds} 次 TPS")
        if r_seg > max(DEFORM_BUDGET_MS, DEFORM_MS_PER_MB * mb):
            failures.append(f"{w}x{h} 形变段 {r_seg:.3f} ms 超预算 "
                            f"{max(DEFORM_BUDGET_MS, DEFORM_MS_PER_MB * mb):.2f}")
        # 不退化：开了形变的整帧增量必须就是形变段那笔，不能把滤波/分带拖下水
        if r_tot - n_tot > r_seg + 0.15:
            failures.append(f"{w}x{h} 开形变后整帧多了 {r_tot - n_tot:.3f} ms，"
                            f"比形变段 {r_seg:.3f} ms 多——形变把别的层也拖重算了")
        if c_tot / max(r_tot, 1e-6) < MIN_DEFORM_SPEEDUP:
            failures.append(f"{w}x{h} 常驻只快 {c_tot / max(r_tot, 1e-6):.1f}×，低于 {MIN_DEFORM_SPEEDUP}×")
        print(f"     显存账单：单位场+恒等网格 {vram / 1e6:.2f} MB"
              f"（每 MB 源图多占 {vram / 1e6 / max(mb, 1e-6):.2f} MB）")


def _time_arm(rgb, lm, use_resident, h: int, w: int):
    """返回（整帧 ms、形变段 ms、拖滑块期间解算次数、常驻字节）。

    use_resident=None 是基线臂：建了单但滑块全零，量的是“不开形变时这一帧多少钱”。
    重算臂把解算也放进计时里——上一版只计了 render，于是“重解 TPS”跟“常驻”一样快，
    加速比量出 1.0×：那种判据绿了比红了更坑。
    """
    pipe = make_pipeline(DEV, w, h, rgb)
    pipe.prepare()
    info = pipe.build_deform(lm)
    frames = max(FRAMES, 8)
    amounts = {"slim_face": 0.0, "big_eye": 0.0, "small_chin": 0.0}
    if use_resident is not None:
        pipe.set_deform_amounts(dict(amounts))
    cx, cy, R, _fw, _fh = face_frame(lm, h, w)
    r0, r1 = support_radii(R)
    total = seg = 0.0
    builds0 = pipe.deform_builds
    for i in range(frames):
        a = 0.2 + 0.6 * (i % 100) / 99.0
        if use_resident is not None:
            pipe.set_deform_amounts({"slim_face": a, "big_eye": a * 0.5, "small_chin": a * 0.7})
        t0 = monotonic_ns()
        if use_resident is False:
            # 对照组：每帧按当前 amount 重解一次场，再拿它采样（仍走同一个 warp_t）
            acc = None
            for kind, amt in (("slim_face", a), ("big_eye", a * 0.5), ("small_chin", a * 0.7)):
                P, D, _m = controls(lm, kind, amt, h, w)
                f = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), h, w,
                                cx=cx, cy=cy, R=r1, r0=r0, device=pipe.device)
                acc = f if acc is None else acc + f
            pipe.deform_units = {"slim_face": acc[None]}
            pipe.deform_amounts = {"slim_face": 1.0, "big_eye": 0.0, "small_chin": 0.0}
        pipe.render(0.5)
        if pipe.device.type != "cpu":
            torch.cuda.synchronize(pipe.device)
        total += (monotonic_ns() - t0) / 1e6
        seg += float(pipe.last_deform_ms)
    builds = pipe.deform_builds - builds0
    out = (total / frames, seg / frames, builds, info["bytes_deform"])
    del pipe
    return out


# ============================================================ 4 反向门禁
def part_reverse_gates(failures: list[str]) -> None:
    """每条判据都得有"错实现必须红"的陪跑，否则它可能只是恒真。"""
    print("\n=== 4) 反向门禁（错实现必须被抓到）")
    h, w = 240, 192
    rgb = np.full((h, w, 3), 128, np.uint8)
    rgb[:, :, 1] = 90
    yy, xx = np.mgrid[0:h, 0:w]
    rgb[(xx - w // 2) ** 2 + (yy - h // 2) ** 2 < (min(h, w) // 3) ** 2] = (210, 170, 150)
    lm = face.build("template")(rgb).landmarks
    cx, cy, R, fw, fh = face_frame(lm, h, w)
    r0, r1 = support_radii(R)
    P, D, _m = controls(lm, "small_chin", 1.0, h, w)
    good = tps_field_np(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0)

    # 4a 把像素位移直接加到归一化网格上（本轮真抓到的错）
    t = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]).float() / 255.0
    grid_bad = identity_grid(h, w) + torch.from_numpy(good[None].astype(np.float32))
    bad = torch.nn.functional.grid_sample(t, grid_bad, mode="bilinear",
                                          padding_mode="border", align_corners=False)
    ok = warp_t(t, torch.from_numpy(good[None].astype(np.float32)), 1.0)
    d_bad = float((bad - ok).abs().max())
    print(f"  4a 单位错（像素直接加归一化网格）与正确实现的差：{d_bad:.3f}（满量程 0–1）")
    if d_bad < 0.05:
        failures.append("4a 反向门禁失效：单位错与正确实现看不出差别，判据是空的")

    # 4b 去掉紧支撑窗 ⇒ 窗外必须被判据抓到
    nogrid = tps_field_np_no_window(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0)
    outside = np.hypot(xx - cx, yy - cy) >= r1
    leak = float(np.abs(nogrid[outside]).max()) if outside.any() else 0.0
    print(f"  4b 去掉紧支撑窗后窗外最大位移：{leak:.3f} px")
    if leak <= 0.0:
        failures.append("4b 反向门禁失效：不套窗窗外也不动，那条判据是恒真的")

    n_face = len(P) - 8          # 末尾 8 个是边框零锚点，它们的请求必须是 0
    pure = np.zeros((len(P), 2))
    pure[:n_face, 1] = 3.0       # 只要 y 方向位移，x 分量一个不给
    # 4c affine 项转置写反 ⇒ 纯轴判据必须红（本轮真抓到的第一个 bug）。
    # 这一条上一版写成了对源码做字符串 grep：它只匹配 numpy 分支的字面量，torch
    # 分支转置写反时照样绿（1e 只比 GPU↔CPU 差，两边同反就测不出）；而任何等价重构
    # （改个变量名）都会让它**假红**，从而诱导后人把门禁改成更弱的形式。现在按 4b
    # 的做法真摆一份错实现出来。
    for arm, right in (("numpy", tps_field_np(P, pure, h, w, cx=cx, cy=cy, R=r1, r0=r0)),
                       ("torch", tps_field_t(P, pure, h, w, cx=cx, cy=cy, R=r1, r0=r0,
                                             device=DEV))):
        r = right.detach().cpu().numpy() if torch.is_tensor(right) else np.asarray(right)
        gx = float(np.abs(r[..., 0]).max())
        bx = float(np.abs(_tps_transposed_variant(P, pure, h, w, want_t=(arm == "torch"))[..., 0]).max())
        print(f"  4c {arm} 分支：生产实现的纯 y 请求 x 分量 {gx:.3e} px，"
              f"affine 转置写反时 {bx:.4f} px")
        if gx > 1e-9:
            failures.append(f"4c {arm} 生产实现里纯 y 请求冒出了 x 位移（{gx} px）")
        if bx <= 1e-3:
            failures.append(f"4c {arm} 反向门禁失效：转置写反也看不出差别，"
                            "那条纯轴判据在这条分支上是恒真的")


def tps_field_np_no_window(P, D, h, w, *, cx, cy, R, r0, lam=1e-8):
    """tps_field_np 去掉窗的那一份——只给反向门禁用，产品不调它。"""
    from lumaretouch_engine.ops.deform import _tps_field
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    X = np.stack([xx.ravel(), yy.ravel()], axis=1)
    return _tps_field(np.asarray(P, dtype=np.float64), np.asarray(D, dtype=np.float64),
                      X, lam, scale=float(max(h, w))).reshape(h, w, 2)


def _tps_transposed_variant(P, D, h, w, *, want_t: bool):
    """把 affine 项转置写反的那一份 TPS（本轮真 bug 的等价错形）——只给反向门禁用。

    不复用产品函数是因为它已经是对的：反向门禁要的是"错实现必须让判据红"，拿一份
    注定正确的实现去证"判据能抓到错"是空转。坐标与位移同除 max(h,w) 再乘回来，
    与 _tps_field 的各向同性归一同步——不然两条臂比的不是同一个形变。
    """
    from lumaretouch_engine.ops.deform import _u_kernel
    P = np.asarray(P, dtype=np.float64)
    D = np.asarray(D, dtype=np.float64)
    scale = float(max(h, w))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    X = np.stack([xx.ravel(), yy.ravel()], axis=1) / scale
    Ps, Ds = P / scale, D / scale
    n = Ps.shape[0]
    if want_t:
        t = torch.as_tensor
        Pt, Dt, Xt = t(Ps, dtype=torch.float64), t(Ds, dtype=torch.float64), t(X, dtype=torch.float64)
        A = torch.cat([torch.ones(n, 1, dtype=torch.float64), Pt], dim=1)
        L = torch.zeros(n + 3, n + 3, dtype=torch.float64)
        L[:n, :n] = _u_kernel(torch.cdist(Pt, Pt).pow(2))
        L[:n, n:] = A
        L[n:, :n] = A.T
        rhs = torch.zeros(n + 3, 2, dtype=torch.float64)
        rhs[:n] = Dt
        sol = torch.linalg.solve(L + 1e-8 * torch.eye(n + 3, dtype=torch.float64), rhs)
        aff = sol[n:]
        f = _u_kernel(torch.cdist(Xt, Pt).pow(2)) @ sol[:n] + aff[0] + Xt @ aff[1:].T
        return (f * scale).reshape(h, w, 2).numpy()
    A = np.hstack([np.ones((n, 1)), Ps])
    L = np.zeros((n + 3, n + 3))
    L[:n, :n] = _u_kernel(((Ps[:, None, :] - Ps[None, :, :]) ** 2).sum(-1))
    L[:n, n:] = A
    L[n:, :n] = A.T
    rhs = np.zeros((n + 3, 2))
    rhs[:n] = Ds
    sol = np.linalg.solve(L + 1e-8 * np.eye(n + 3), rhs)
    aff = sol[n:]
    f = _u_kernel(((X[:, None, :] - Ps[None, :, :]) ** 2).sum(-1)) @ sol[:n] \
        + aff[0] + X @ aff[1:].T
    return (f * scale).reshape(h, w, 2)


def _sample_bilinear(f, xs, ys):
    """在精确坐标处取场值（双线性），避开"取整像素"本身带来的位置误差。"""
    h, w = f.shape[0], f.shape[1]
    x = np.clip(np.asarray(xs, dtype=np.float64), 0.0, w - 1.0)
    y = np.clip(np.asarray(ys, dtype=np.float64), 0.0, h - 1.0)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    wx = (x - x0)[:, None]
    wy = (y - y0)[:, None]
    return (f[y0, x0] * (1 - wx) * (1 - wy) + f[y0, x1] * wx * (1 - wy)
            + f[y1, x0] * (1 - wx) * wy + f[y1, x1] * wx * wy)


def main() -> int:
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("无 GPU：这份打靶量的是 ROCm 内核与形变的产品通路，退出码 2，不给假绿")
        return 2
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)
    failures: list[str] = []
    print(f"设备={DEV}  重复={REPS}  每次帧数={FRAMES}  预算档={BUDGETS}")
    part_fidelity(failures)
    part_parity(failures)
    part_speed(failures)
    part_reverse_gates(failures)
    if failures:
        print("\nVERDICT=FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nVERDICT=PASS  （动对了地方、窗外一个字节不动、缩放与重解是同一件事，而且快 8× 以上）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
