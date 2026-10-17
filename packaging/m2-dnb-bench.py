#!/usr/bin/env python3
"""M2-a2 离线打靶：中性灰修容到底动没动对地方、快没快在对地方，不起 GUI。

主张有两句，缺一句都不算成立：

  1) **它动的是光影，不是纹理，也不是"刷一块色"。** 三件事各自要有一个数：
     · 档数：线性光下逐像素比值必须精确等于 2^(exposure·带限场)。这是"在线性光下做"
       的可证伪形式——在 sRGB 编码值上乘同一个乘子会漂出几分之一档，而且**漂多少
       取决于底色**（探针在真图上实测 p99 漂 0.75 档）。
     · 纹理：修容前后细带（毛孔/雀斑那一层）的能量比应当等于乘子本身的幂律预测，
       而不是"被抹平"。拿"细带保留率≥0.97"当判据是错的：乘性曝光提亮一档，纹理
       绝对幅度本来就该涨，保留率必然 >1。
     · 笔触不可见：带限半径 r 把硬边笔刷的边缘跳变压到与盘心改动同量级。
       这一条专门防"其实是拿笔刷一块色"——只量档数是抓不到它的。
  2) **快，而且算的是同一件事。** "db 结果常驻"与"每帧重算 db"两条臂的上屏字节
     必须逐字节相等；拖 strength 期间 db 一次都不重算。

臂之间交替跑，避免机器热漂移单边占便宜；口径沿用 m1-drag-bench / m2-skin-bench。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_rgb                    # noqa: E402
from lumaretouch_engine.ops.guided import _box_np                 # noqa: E402
from lumaretouch_engine.ops.light import (dodge_burn_np, dodge_burn_t, DEFAULT_DB_RADIUS)
from lumaretouch_engine.quant import quantize_np                  # noqa: E402
from lumaretouch_engine.server import Engine, monotonic_ns        # noqa: E402
from lumaretouch_engine.shm import FrameShm, shm_name             # noqa: E402
from lumaretouch_engine.vram import LightOp, make_pipeline        # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "7"))
FRAMES = int(os.environ.get("LRT_FRAMES", "40"))
DEV = os.environ.get("LRT_DEVICE", "cuda")
OUT_DIR = os.environ.get("LRT_OUT", os.path.join(HERE, "..", "build", "m2-dnb"))

# ---- 判据（全是实测量纲，推导见 test_light / test_protocol 里同名的那几条）----
STOP_TOL = 1e-5          # float64 CPU 参考的逐像素档数中位比容差
STOP_TOL_GPU = 2e-3      # float32 GPU 生产路径的容差（实测漂到 5e-4～1.6e-3）
SRGB_DRIFT_MIN = 0.05    # 反向门禁：sRGB 域乘的档数漂移必须至少这么大，否则判据是空的
EDGE_SUP_MIN = 3.0       # 带限把笔触边缘跳变压掉的最低倍数
FINE_BAND_MIN = 0.97     # 细带能量不被抹平（乘性曝光下实测 ≥1，留一点余量）
MIX_BUDGET_MS = 1.0      # 拖 strength 的每帧预算（M1-3c 既定线，不许被 M2-a2 弄退化）
MIX_MS_PER_MB = float(os.environ.get("LRT_MIX_MS_PER_MB", "0.30"))
DB_BUDGET_MS = 12.0      # 改一次修容参数（两份 db 重算）的每事件预算下限
DB_MS_PER_MB = float(os.environ.get("LRT_DB_MS_PER_MB", "3.0"))
MIN_DB_SPEEDUP = 3.0     # 每帧重算 db ÷ 常驻命中 的最低加速比
# 产品默认带限半径从库里转发，不在这里写字面量：M1-2 那次「默认值改了但调用方
# 还带着旧字面量」的同构坑，各跑靶不能再踩一遍
DEFAULT_R = DEFAULT_DB_RADIUS
Q = quantize_np


def chw(a):
    if a.ndim == 2:
        return np.ascontiguousarray(a[None, None])
    return np.ascontiguousarray(a.transpose(2, 0, 1))[None]


def lin(a):
    a = np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def strokes(h, w):
    """两支笔：额头/鼻梁减淡 + 两颊加深，值域 [-1,1]。

    用**硬边**圆盘而不是平滑高斯：产品真实输入就是硬边 RLE（mask_from_rle 出来的
    0/255 加 feather≤8 的窄羽化）。拿平滑场当笔触，带限带不带根本看不出区别。
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    f = np.zeros((h, w))
    for cy, cx, rad, sign in ((0.26, 0.50, 0.15, +1.0), (0.55, 0.32, 0.09, -1.0),
                              (0.55, 0.68, 0.09, -1.0)):
        f[((yy - h * cy) ** 2 + (xx - w * cx) ** 2) <= (w * rad) ** 2] = sign
    return f


# ============================================ 第一部分：动的是光影，不是别的
def part_semantics(failures):
    print("\n══ M2-a2-1 语义：档数 / 纹理 / 笔触可见性（672×848 真图代理档）")
    d = load_rgb(FIXTURE)
    h, w = d.h, d.w
    rgb = d.rgb
    x64 = rgb.astype(np.float64) / 255.0
    x32 = chw(rgb.astype(np.float32) / 255.0)
    f = strokes(h, w)
    fc = chw(f)
    pipe = make_pipeline(DEV, w, h, rgb)

    def ops_for(field):
        """把带符号场拆成两支笔（减淡一笔 + 加深一笔）。

        上一版这里只挂了一支 sign=+1、weight=|f| 的笔，把两支加深笔也变成了减淡，
        而下面与它对比的 CPU 参考用的是带符号的完整场——两个臂算的根本不是
        同一个东西，于是一口气报出 83 LSB 差与 +2.7 LSB 系统偏移。产品通路里 UI 就是一笔
        一个方向，拆两支才是真实形状；顺便也把“场线性累加”这条在生产通路上验了。
        """
        up = np.round(np.clip(field, 0.0, 1.0) * 255.0).astype(np.uint8)
        dn = np.round(np.clip(-field, 0.0, 1.0) * 255.0).astype(np.uint8)
        out = []
        if int((up > 0).sum()):
            out.append(LightOp(op_id=1, weight=up, sign=1))
        if int((dn > 0).sum()):
            out.append(LightOp(op_id=2, weight=dn, sign=-1))
        return out

    def prod(exposure, radius, field=None):
        """走 PreviewPipeline —— 引擎每帧走的那一条，不是探针手拼。"""
        f_use = f if field is None else field
        pipe.drop_cache()
        pipe.set_light_params(exposure, radius)
        pipe.set_light_ops(ops_for(f_use))
        pipe.prepare()      # 成品得先备好：lighten_result() 的入参就是它
        return pipe.lighten_result()[0].cpu().numpy().transpose(1, 2, 0)

    # ---- 1a 档数精确性 ----
    # 容差分两档不是放水：float64 参考能到 1e-5（test_light 里实测 MAD 4e-8），
    # 而 GPU 生产路径的 pow 在 float32 下就是会漂到 5e-4 量级。两个数分开报，
    # 才能看出“剩下那点差”是实现精度而不是算法错。
    print(f"  {'exposure':>9s}{'radius':>7s}{'GPU(float32) 实测/解析':>22s}"
          f"{'CPU参考(float64)':>18s}{'sRGB域乘的漂移p99':>18s}")
    for e, r in ((0.6, 24), (1.0, 24), (-0.6, 24), (0.3, 12), (1.5, 48)):
        out = prod(e, r).astype(np.float64)
        ref = dodge_burn_np(x32, field=fc, exposure=e, radius=r)[0].transpose(1, 2, 0) \
            .astype(np.float64)
        ws = _box_np(fc, r)[0, 0]
        want = np.power(2.0, e * ws)
        wr = np.repeat(want[..., None], 3, axis=2)
        Li = lin(x64)
        m0 = (np.abs(ws) > 0.05)[..., None] & (Li > 1e-3)
        meds = []
        for arr in (out, ref):
            Lo = lin(arr)
            m = m0 & (Lo < 1.0 - 1e-6)
            meds.append(float(np.median(Lo[m] / Li[m] / wr[m])))
        # 反向对照：同一个乘子直接作用在 sRGB 编码值上，档数会漂多少
        naive = np.clip(x64 * wr, 0.0, 1.0)
        Ln = lin(naive)
        mn = (wr > 1.05) & (Li > 3e-4) & (Ln < 1.0 - 1e-6) & (Li < 0.90)
        drift = float(np.percentile(np.abs(np.log2(Ln[mn] / Li[mn]) - np.log2(wr[mn])), 99))
        print(f"  {e:9.2f}{r:7d}{meds[0]:22.6f}{meds[1]:18.6f}{drift:18.3f} 档")
        if abs(meds[0] - 1.0) > STOP_TOL_GPU:
            failures.append(f"exposure={e} radius={r}：GPU 档数偏了 {meds[0]:.6f}，"
                            f"超 float32 实现精度容差 {STOP_TOL_GPU}")
        if abs(meds[1] - 1.0) > STOP_TOL:
            failures.append(f"exposure={e} radius={r}：CPU 参考档数偏了 {meds[1]:.6f}，"
                            f"不是精确乘曝光（float64 没理由漂这么多）")
        if drift < SRGB_DRIFT_MIN:
            failures.append(f"sRGB 域乘的档数漂移只有 {drift:.3f} 档，上面那条判据是恒真的")

    # ---- 1b 纹理不被抹平 ----
    print("\n  细带（毛孔/雀斑那一层，box r=4）能量比：")
    fine_ref = float((x64 - _box_np(chw(x64.astype(np.float32)), 4)[0].transpose(1, 2, 0)).std())
    for e, r in ((0.6, 24), (-0.6, 24), (0.6, 4), (0.6, 0)):
        out = prod(e, r).astype(np.float64)
        fine = float((out - _box_np(chw(out.astype(np.float32)), 4)[0].transpose(1, 2, 0)).std())
        m = np.abs(f) > 0.5
        print(f"    exposure={e:+.2f} radius={r:2d}: 细带 ×{fine / fine_ref:.3f}"
              f"（笔区内 std {float(out[m].std() / x64[m].std()):.3f}）")
        if fine / fine_ref < FINE_BAND_MIN:
            failures.append(f"exposure={e} radius={r}：细带能量只剩 {fine / fine_ref:.3f}，纹理被抹平了")

    # ---- 1c 笔触不可见 ----
    print("\n  笔触边缘跳变 vs 盘心改动（LSB）：")
    ref_q = Q(x64).astype(np.int32)
    jumps = {}
    for r in (0, 6, 12, 24, 48):
        out = prod(0.6, r)
        dd = Q(out).astype(np.int32) - ref_q
        row = dd[int(h * 0.26), :, 0]
        edge = int(np.abs(np.diff(row)).max())
        center = int(np.abs(dd[int(h * 0.26), int(w * 0.50)]).max())
        jumps[r] = (edge, center)
        print(f"    radius={r:2d}: 边缘 {edge:3d} LSB，盘心 {center:3d} LSB")
    if jumps[0][0] < EDGE_SUP_MIN * jumps[DEFAULT_R][0]:
        failures.append(f"带限只把边缘压了 {jumps[0][0] / max(jumps[DEFAULT_R][0], 1):.1f} 倍，"
                        f"低于 {EDGE_SUP_MIN}：笔触仍然看得见")
    if jumps[DEFAULT_R][0] > 1.5 * jumps[DEFAULT_R][1]:
        failures.append(f"radius={DEFAULT_R} 时边缘跳变 {jumps[DEFAULT_R][0]} 仍是盘心 "
                        f"{jumps[DEFAULT_R][1]} 的 {jumps[DEFAULT_R][0] / max(jumps[DEFAULT_R][1], 1):.1f} 倍")

    # ---- 1d GPU 生产 vs CPU 参考：不许有系统性偏移 ----
    # 两个臂必须入同一个操作数：prod() 走的是 db(磨皮成品)，上一版拿原图当 CPU 参考，
    # 两个臂比的是“磨皮前后的差”，于是报出 26 LSB——那不是精度问题，是在量两件事。
    print("\n  GPU 生产实现 vs CPU 参考（同一操作数、同一带符号场）：")
    for e, r in ((0.6, 24), (1.2, 24), (-0.6, 12), (0.3, 48)):
        g = prod(e, r)                     # 返回的就是 db(成品)，成品同时留在 pipe.retouched 上
        res_np = pipe.retouched[0].cpu().numpy().transpose(1, 2, 0)
        c = dodge_burn_np(chw(res_np), field=chw(f), exposure=e, radius=r)[0].transpose(1, 2, 0)
        dd = Q(g).astype(np.int32) - Q(c).astype(np.int32)
        cont = float(np.abs(g - c).max())
        print(f"    exposure={e:+.2f} radius={r:2d}: 最大 {int(np.abs(dd).max())} LSB，"
              f"差异子像素 {(dd != 0).mean():6.3%}，系统偏移 {dd.mean():+.5f} LSB，"
              f"连续域最大差 {cont:.2e}")
        if int(np.abs(dd).max()) > 1:
            failures.append(f"exposure={e} radius={r}：GPU 与 CPU 参考差 {int(np.abs(dd).max())} LSB"
                            f"（连续域 {cont:.1e}）")
        if abs(float(dd.mean())) > 0.02:
            failures.append(f"exposure={e} radius={r}：有 {dd.mean():+.4f} LSB 系统偏移"
                            f"（最大 1 LSB 掩盖不住整幅偏暗/偏亮）")

    # ---- 1e 场恰好为零区逐字节不动 ----
    # 口径卡在“带限场恰好为零”，不是“我画的几何圆外”：盒式带限有合法拖尾，
    # 真图代理档上三支笔之外仍有 0.30% 像素 ws≠0（|ws| 最大 0.0087 → 增益 1.0036
    # → 1 LSB）。上一轮拿圆外当笔外，量到一个“圈外仍差 1 LSB”就以为发现了缺陷，
    # 又把当时其实需要的 `where(ws == 0, ...)` 守卫撤了——两头都错：
    # 拖尾是合法的，而 ws=0 处的重量化是真的（操作数不在 256 格点上，往返不恒等）。
    print("\n  场恰好为零区的字节保真（生产通路，db(成品) vs 成品）：")
    for e, r in ((0.6, 24), (1.2, 48), (-0.6, 12)):
        g = prod(e, r)
        res_np = pipe.retouched[0].cpu().numpy().transpose(1, 2, 0)
        ws = _box_np(fc, r)[0, 0]
        zero = ws == 0.0
        if float(zero.mean()) < 0.3:
            failures.append(f"radius={r}：场为零的区域只占 {zero.mean():.1%}，这条没在验零增益区")
        dd = np.abs(Q(g).astype(np.int32) - Q(res_np).astype(np.int32)).max(axis=2)
        print(f"    exposure={e:+.2f} radius={r:2d}: 场为零区占 {zero.mean():5.1%}，"
              f"其中最大 {int(dd[zero].max())} LSB，非零像素 {(dd[zero] > 0).mean():.4%}")
        if int(dd[zero].max()) != 0:
            failures.append(f"exposure={e} radius={r}：场为零的地方被重量化了 "
                            f"{int(dd[zero].max())} LSB——gain 在 ws=0 处就是 1.0，不该动字节")


# ==================================== 第二部分：db 常驻的每帧成本与字节对拍
def new_engine(dev, rgb, w, h, tag):
    eng = Engine(f"m2-dnb-{os.getpid()}-{tag}")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    pipe = make_pipeline(dev, w, h, rgb)
    eng._vram = pipe
    eng._src_rgb = rgb
    eng._image_loaded = True
    name = shm_name(f"lrt-dnb-{os.getpid()}-{tag}-{w}x{h}")
    shm = FrameShm(name, w, h, slots=2, create=True)
    return eng, pipe, shm


def run_arm(eng, pipe, shm, frames, mode, rgb, f):
    """mode: none=没画修容 / cached=画了但常驻命中 / recompute=每帧重算 db。"""
    ks, last, lights = [], None, 0
    up = np.round(np.clip(f, 0.0, 1.0) * 255.0).astype(np.uint8)
    dn = np.round(np.clip(-f, 0.0, 1.0) * 255.0).astype(np.uint8)
    ops = ([LightOp(op_id=1, weight=up, sign=1), LightOp(op_id=2, weight=dn, sign=-1)]
           if mode != "none" else [])
    pipe.drop_cache()
    pipe.set_light_ops(ops)
    for i in range(frames):
        strength = 0.25 + 0.5 * (i % 100) / 99.0
        if mode == "recompute":
            # 每帧把两份 db 结果丢掉，逼它重算——这才是"没有常驻层"时的真实成本
            pipe.light_src = None
            pipe.light_src_key = None
            pipe.light_res = None
            pipe.light_res_key = None
        t0 = monotonic_ns()
        pixels, seg = eng._make_frame(shm, i, "image_stream", pipe)
        eng._sync()
        ks.append(seg["filter"] + seg["light"] + seg["kernel"])
        if seg["light"] > 0:
            lights += 1
        if mode == "recompute" and seg["light"] <= 0:
            raise SystemExit(f"每帧重算臂第 {i} 帧没重算 db——两臂在量同一条路")
        if mode == "cached" and i > 0 and seg["light"] > 0:
            raise SystemExit(f"常驻臂第 {i} 帧重算了 db：缓存键算错了，零重算不成立")
        last = pixels.copy()
    return ks, last, lights


def part_speed(failures):
    print("\n══ M2-a2-2 分层常驻：三档代理 × 三条臂（同轮交替，抗机器热漂移）")
    med = lambda xs: statistics.median(xs)  # noqa: E731
    for budget in BUDGETS:
        d = load_rgb(FIXTURE, budget=budget)
        f = strokes(d.h, d.w)
        eng, pipe, shm = new_engine(DEV, d.rgb, d.w, d.h, "spd")
        print(f"── 代理档 {d.w}x{d.h}（{(d.w * d.h * 4) / 1e6:.2f} MB/帧）")
        try:
            acc = {"none": [], "cached": [], "recompute": []}
            lastb = {}
            for _ in range(REPS):
                for mode in ("none", "cached", "recompute"):
                    ks, last, _n = run_arm(eng, pipe, shm, FRAMES, mode, d.rgb, f)
                    acc[mode].append(med(ks))
                    lastb[mode] = last
            a, b, c = med(acc["none"]), med(acc["cached"]), med(acc["recompute"])
            mb = (d.w * d.h * 4) / 1e6
            mix_budget = max(MIX_BUDGET_MS, MIX_MS_PER_MB * mb)
            db_budget = max(DB_BUDGET_MS, DB_MS_PER_MB * mb)
            sp = c / max(b, 1e-9)
            print(f"   无修容 {a:.3f} ms → 修容常驻 {b:.3f} ms → 每帧重算 db {c:.3f} ms"
                  f"（{sp:.1f}x）；拖 strength 预算 {mix_budget:.2f} ms，"
                  f"改档数预算 {db_budget:.2f} ms")
            print(f"   常驻账单：修容层 {pipe.light_resident_bytes() / 2 ** 20:.1f} MiB")
            if b > mix_budget:
                failures.append(f"{d.w}x{d.h}：有修容层时拖 strength 每帧 {b:.3f} ms "
                                f"超预算 {mix_budget:.2f} ms")
            if c > db_budget:
                failures.append(f"{d.w}x{d.h}：每帧重算 db {c:.3f} ms 超预算 {db_budget:.2f} ms")
            if sp < MIN_DB_SPEEDUP:
                failures.append(f"{d.w}x{d.h}：db 常驻只带来 {sp:.1f}x，低于 {MIN_DB_SPEEDUP}x")
            if not np.array_equal(lastb["cached"], lastb["recompute"]):
                diff = int(np.abs(lastb["cached"].astype(np.int16)
                                  - lastb["recompute"].astype(np.int16)).max())
                failures.append(f"{d.w}x{d.h}：常驻臂与每帧重算臂上屏字节不同（最大 {diff} LSB）")
            else:
                print("   字节对拍：常驻臂与每帧重算臂逐字节相等 ✓")
            # 无修容那一臂只当基线用：它与有修容的两臂本来就该不同字节，不比
        finally:
            shm.close()
            try:
                os.unlink(f"/dev/shm/{shm_name(f'lrt-dnb-{os.getpid()}-spd-{d.w}x{d.h}')}")
            except FileNotFoundError:
                pass


# ================================================== 第三部分：对照图（真图）
def part_reference_images():
    from PIL import Image

    os.makedirs(OUT_DIR, exist_ok=True)
    d = load_rgb(FIXTURE)
    pipe = make_pipeline(DEV, d.w, d.h, d.rgb)
    f = strokes(d.h, d.w)
    weight = np.round(np.abs(f) * 255).astype(np.uint8)

    def shot(exposure, ops):
        pipe.drop_cache()
        pipe.set_light_params(exposure, DEFAULT_R)
        pipe.set_light_ops(ops)
        return pipe.retouch(1.0)[0].cpu().numpy().transpose(1, 2, 0)

    dodge = [LightOp(op_id=1, weight=np.round(np.clip(f, 0, 1) * 255).astype(np.uint8), sign=1)]
    burn = [LightOp(op_id=2, weight=np.round(np.clip(-f, 0, 1) * 255).astype(np.uint8), sign=-1)]
    panels = [("1 原图", None), ("2 只减淡 0.6 档", (dodge, 0.6)),
              ("3 只加深 0.6 档", (burn, 0.6)), ("4 三支笔全上（额亮脸收）", (dodge + burn, 0.6))]
    shots = []
    for label, spec in panels:
        if spec is None:
            arr = d.rgb.astype(np.float32) / 255.0
        else:
            ops, e = spec
            pipe.drop_cache()
            pipe.set_light_params(e, DEFAULT_R)
            pipe.set_light_ops(ops)
            arr = pipe.retouch(1.0)[0].cpu().numpy().transpose(1, 2, 0)
        shots.append((label, np.clip(arr, 0, 1)))
    print("\n══ M2-a2-3 对照图（真图代理档）")
    y0, y1, x0, x1 = int(d.h * 0.16), int(d.h * 0.38), int(d.w * 0.36), int(d.w * 0.66)
    tiles = []
    for label, arr in shots:
        c = (arr[y0:y1, x0:x1] * 255).astype(np.uint8)
        tiles.append(np.asarray(Image.fromarray(c).resize(((x1 - x0) * 2, (y1 - y0) * 2),
                                                          Image.NEAREST)))
        # 线性光均值比 = 实测档数；细带 std = 纹理有没有被糊
        Li = lin(d.rgb[y0:y1, x0:x1].astype(np.float64) / 255.0)
        Lo = lin(arr[y0:y1, x0:x1].astype(np.float64))
        stops = float(np.log2(Lo.mean() / Li.mean()))
        print(f"   {label:22s} 额头区实测 {stops:+.3f} 档")
    grid = np.concatenate([np.concatenate([t, np.full((t.shape[0], 6, 3), 24, np.uint8)], axis=1)
                           for t in tiles], axis=1)
    out = os.path.join(OUT_DIR, "compare-forehead.png")
    Image.fromarray(grid).save(out)
    print(f"   文件：{out}")


def main() -> int:
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("无 GPU：这份打靶量的是 ROCm 内核与修容的产品通路，退出码 2，不给假绿")
        return 2
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    failures: list[str] = []
    print(f"设备={DEV}  重复={REPS}  每次帧数={FRAMES}")
    part_semantics(failures)
    part_speed(failures)
    part_reference_images()
    if failures:
        print("\nVERDICT=FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nVERDICT=PASS  （档数精确、纹理没被糊、笔触看不见，而且快的与算的是同一件事）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
