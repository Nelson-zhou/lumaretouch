#!/usr/bin/env python3
"""M2-a 离线打靶：质感磨皮到底保没保住毛孔、分层缓存省下多少，不起 GUI。

这一节的主张有两句，缺一句都不算成立：

  1) **「磨皮后毛孔细节保留」必须是个数，不是形容词。**
     只看频带能量比例会骗人：整幅图的细带/中带能量被发丝、眼睛、背景边缘占着，
     那些东西本来就不该动（导向滤波保边），于是真实人像上"中带只降了 6%"这种
     看不出任何东西的数会堂而皇之过关。所以这里造一张**成分已知**的皮肤靶：
     平坦底色 + 半径 9~14 的高斯斑（中带）+ σ=0.013 的稠密颗粒（细带，毛孔的替身）
     + 一条 0.06 的阶跃硬边缘，再用最小二乘把每条成分的**真实增益**回归出来。
     回归自变量是精确已知的注入数组，串扰进不来。
  2) **快，而且算的是同一件事。** 「每帧全重算」与「只重组」两条臂的上屏字节必须
     逐字节相等；否则"分层缓存"就是偷偷换了算法。

臂之间交替跑，避免机器热漂移单边占便宜；口径沿用 m1-drag-bench / m1-inpaint-bench。
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
from lumaretouch_engine.ops.guided import _box_np, guided_np, retouch_np   # noqa: E402
from lumaretouch_engine.server import Engine, monotonic_ns   # noqa: E402
from lumaretouch_engine.shm import FrameShm, shm_name        # noqa: E402
from lumaretouch_engine.vram import make_pipeline            # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "7"))
FRAMES = int(os.environ.get("LRT_FRAMES", "40"))
DEV = os.environ.get("LRT_DEVICE", "cuda")
OUT_DIR = os.environ.get("LRT_OUT", os.path.join(HERE, "..", "build", "m2-skin"))
NOISE_MS = float(os.environ.get("LRT_NOISE_MS", "0.05"))

# ---- 判据（全是实测量纲，不是许愿值；推导见 test_guided 里同名的那几条）----
PORE_MIN = 0.95          # 默认位细带增益下界：低于它就是"塑料脸"
BLEM_MAX = 0.55          # 默认位中带增益上界：高于它就是"磨皮没干活"
EDGE_MIN = 0.80          # 硬边缘对比保留下界：磨皮不许把结构画圆
PLASTIC_PORE_MAX = 0.20  # 传统盒式模糊基线的细带增益上界：证明 PORE_MIN 不是恒真门禁
GAIN_BUDGET_MS = 1.5     # 拖"匀肤/细节/肌理"的每帧预算下限（产品代理档）
# 重组这一步是纯访存（读四条带 + 写一份成品），以字节为唯一因子——M1-1 已经钉死去过
# 一次“拿固定常数当带宽预算”的错误。实测斜率（产品档 0.534 ms / 2.28 MB = 0.234，
# 全尺寸档 1.687 / 5.24 = 0.32，小档 0.254 / 0.81 = 0.31 ms/MB），给到 0.45 的余量。
GAIN_MS_PER_MB = float(os.environ.get("LRT_GAIN_MS_PER_MB", "0.45"))
MIX_BUDGET_MS = 1.0      # 拖强度的每帧预算（M1-3c 的既定线，不许被 M2 弄退化）
MIX_MS_PER_MB = float(os.environ.get("LRT_MIX_MS_PER_MB", "0.30"))
MIN_GAIN_SPEEDUP = 3.0   # 每帧全重算 ÷ 只重组 的最低加速比
Q = lambda a: (np.clip(a, 0, 1) * 255).astype(np.uint8).astype(np.int16)  # noqa: E731


def chw(a):
    """(H,W) 或 (H,W,C) → (1,C,H,W)。"""
    if a.ndim == 2:
        return np.ascontiguousarray(a[None, None])
    return np.ascontiguousarray(a.transpose(2, 0, 1))[None]


# ============================================================ 成分已知的皮肤靶
def skin_target(h, w, seed=20261016):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    base = 0.62 + 0.03 * np.sin(2 * np.pi * xx / (w * 0.45)) + 0.05 * (yy / h)
    blemish = np.zeros((h, w))
    for _ in range(int(h * w / 14000)):        # 密度随面积走，小图也要有足够样本
        cy, cx = int(rng.integers(18, h - 18)), int(rng.integers(18, w - 18))
        rad = float(rng.uniform(9.0, 14.0))
        blemish += float(rng.normal(0.0, 0.035)) * np.exp(
            -((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * rad * rad))
    pore = rng.normal(0.0, 0.013, size=(h, w)) * rng.random((h, w)) ** 0.5
    edge = 0.06 * ((xx > w * 0.72) & (yy > 60) & (yy < h - 60)).astype(np.float64)
    return base, blemish, pore, edge, np.clip(base + blemish + pore + edge, 0.0, 1.0)


def band_gains(out, comps):
    """最小二乘回归出各成分的真实增益：返回 (孔, 斑, 边, 最大残差)。"""
    base, blemish, pore, edge = comps
    o = np.asarray(out).ravel() if np.asarray(out).ndim <= 2 else np.asarray(out)[0, 0].ravel()
    X = np.stack([np.ones(o.size), base.ravel(), blemish.ravel(),
                  pore.ravel(), edge.ravel()], 1)
    beta, *_ = np.linalg.lstsq(X, o, rcond=None)
    return float(beta[3]), float(beta[2]), float(beta[4]), float(np.abs(o - X @ beta).max())


# ================================================== 第一部分：质感保留（决定性）
def part_retention(failures):
    print("\n══ M2-a-1 质感保留：成分已知皮肤靶上的带增益（672×848，走产品通路）")
    base, blemish, pore, edge, img = skin_target(848, 672)
    comps = (base, blemish, pore, edge)
    # 关键：靶子先过一遍 uint8（引擎吃的就是 uint8 代理帧），后面所有臂与回归都在
    # 这份量化后的数据上进行——否则"产品通路"与"报表"比的不是同一张图。
    rgb_u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    rgb_u8 = np.dstack([rgb_u8] * 3)
    x64 = rgb_u8.astype(np.float64) / 255.0
    x32 = rgb_u8.astype(np.float32) / 255.0
    xc = chw(x32)
    pipe = make_pipeline(DEV, 672, 848, rgb_u8)

    def prod(gains, strength=1.0):
        """走 PreviewPipeline.retouch —— 就是引擎每帧走的那一条，不是探盘手拼。"""
        pipe.drop_cache()
        return pipe.retouch(strength, **gains)[0].cpu().numpy().transpose(1, 2, 0)[:, :, 0]

    arms = [
        ("原图（回归自校，必须 1.000）", "self"),
        ("盒式模糊 r=4（传统磨皮）", ("blur", 4)),
        ("盒式模糊 r=8（传统磨皮）", ("blur", 8)),
        ("盒式模糊 r=12（传统磨皮）", ("blur", 12)),
        ("M1-3c 口径（残差带×0.85）", "m13c"),
        ("M2-a 默认（broad0/mid0/tex1）", {}),
        ("M2-a 强度 0.75（产品常用位）", {"_s": 0.75}),
        ("M2-a tex=0（塑料脸对照）", {"detail_gain": 0.0}),
        ("M2-a 恒等位（三增益全 1）", {"broad_gain": 1.0, "mid_gain": 1.0}),
    ]
    print(f"  {'臂':34s}{'孔增益':>9s}{'斑增益':>9s}{'边缘增益':>10s}{'选择性':>9s}{'平均改动':>11s}")
    got = {}
    for label, spec in arms:
        if spec == "self":
            arr = x64[:, :, 0]
        elif isinstance(spec, tuple) and spec[0] == "blur":
            arr = _box_np(xc, spec[1])[0].transpose(1, 2, 0)[:, :, 0].astype(np.float64)
        elif spec == "m13c":
            low1 = guided_np(xc, 12, 6e-4)
            low2 = guided_np(low1, 24, 2.4e-3)
            arr = (low2 + (xc - low1) * 0.85)[0].transpose(1, 2, 0)[:, :, 0].astype(np.float64)
        else:
            gains = dict(spec)
            s = gains.pop("_s", 1.0)
            arr = prod(gains, strength=s).astype(np.float64)
        pk, bl, eg, resid = band_gains(arr, comps)
        got[label] = (pk, bl, eg)
        dlsb = float(np.abs(Q(arr) - Q(x64[:, :, 0])).mean())
        print(f"  {label:34s}{pk:9.3f}{bl:9.3f}{eg:10.3f}{pk/max(abs(bl),1e-9):9.2f}{dlsb:9.2f} LSB")

    # GPU 生产路径与 CPU 参考必须落在同一字节上（否则报表上的数是探盘的，不是产品的）
    ref = retouch_np(xc, strength=1.0)
    gpu = pipe.retouch(1.0)[0].cpu().numpy()
    b = np.abs(Q(gpu) - Q(ref))
    ratio = float((b > 0).mean())
    print(f"  产品默认位 GPU↔CPU 参考：最大 {int(b.max())} LSB，差异子像素 {ratio*100:.3f}%")
    if int(b.max()) > 1:
        failures.append(f"产品默认位 GPU 与 CPU 参考差 {int(b.max())} LSB，超验收口径")
    if ratio > 0.005:
        failures.append(f"产品默认位有 {ratio:.2%} 子像素在差，1 LSB 掩盖了系统性偏移")

    pk0, bl0, eg0 = got["原图（回归自校，必须 1.000）"]
    if not (abs(pk0 - 1) < 0.02 and abs(bl0 - 1) < 0.02 and abs(eg0 - 1) < 0.02):
        failures.append(f"回归自校就坏了（孔{pk0:.3f} 斑{bl0:.3f} 边{eg0:.3f}）——本部分作废")
        return
    KEY = "M2-a 默认（broad0/mid0/tex1）"
    pk, bl, eg = got[KEY]
    if pk < PORE_MIN:
        failures.append(f"默认位细带增益 {pk:.3f} < {PORE_MIN}：磨皮把毛孔抹掉了")
    if bl > BLEM_MAX:
        failures.append(f"默认位中带增益 {bl:.3f} > {BLEM_MAX}：磨皮没去掉色斑")
    if eg < EDGE_MIN:
        failures.append(f"默认位硬边缘对比保留 {eg:.3f} < {EDGE_MIN}：结构被画圆了")
    for lbl in ("盒式模糊 r=4（传统磨皮）", "盒式模糊 r=8（传统磨皮）", "盒式模糊 r=12（传统磨皮）"):
        if got[lbl][0] > PLASTIC_PORE_MAX:
            failures.append(f"{lbl} 细带还剩 {got[lbl][0]:.3f} > {PLASTIC_PORE_MAX}："
                            f"基线没照出'塑料脸'，PORE_MIN 那条成了恒真门禁")
    lin, old = got[KEY], got["M1-3c 口径（残差带×0.85）"]
    if lin[0] < old[0] + 0.05:
        failures.append(f"线性纹理带没比 guided 残差带更保孔（{lin[0]:.3f} vs {old[0]:.3f}）")
    if lin[1] > old[1]:
        failures.append(f"线性纹理带没比 guided 残差带更去斑（{lin[1]:.3f} vs {old[1]:.3f}）")
    flat = got["M2-a tex=0（塑料脸对照）"]
    if flat[0] > 0.15:
        failures.append(f"detail_gain=0 后细带还剩 {flat[0]:.3f}，肌理旋钮是空的")
    ident = got["M2-a 恒等位（三增益全 1）"]
    if min(ident) < 0.97 or max(ident) > 1.03:
        failures.append(f"恒等位不恒等：{ident}")
    print(f"  判据：孔≥{PORE_MIN} 斑≤{BLEM_MAX} 边≥{EDGE_MIN}；基线孔≤{PLASTIC_PORE_MAX}；"
          f"默认位 vs M1-3c 孔差 ≥0.05 且斑更低")


# ============================================= 第二部分：分层缓存的每帧成本
def new_engine(dev, rgb, w, h, tag):
    eng = Engine(f"m2-skin-{os.getpid()}-{tag}")
    eng.device = dev
    eng._torch = torch
    eng._cuda = dev.startswith("cuda") and torch.cuda.is_available()
    pipe = make_pipeline(dev, w, h, rgb)
    eng._vram = pipe
    eng._src_rgb = rgb
    eng._image_loaded = True
    name = shm_name(f"lrt-skin-{os.getpid()}-{tag}-{w}x{h}")
    shm = FrameShm(name, w, h, slots=2, create=True)
    return eng, pipe, shm


# 两层缓存的清理口径由库里给（PreviewPipeline.drop_cache / drop_product）：
# 各跑靶自己写赋值，就是 M1-2 那次“调用方自带一份默认值”的同构坑。
drop_all = lambda pipe: pipe.drop_cache()        # noqa: E731
# 只丢成品：下一次 prepare 命中分带、只重跑重组——这就是 M2-a 新增的热路径。
drop_product = lambda pipe: pipe.drop_product()  # noqa: E731


def run_arm(eng, pipe, shm, frames, mode, gains):
    """mode: all=每帧全重算（分带也丢）/ combine=只重组 / mix=全常驻只混合。"""
    ks, last, rebands = [], None, 0
    for i in range(frames):
        if mode == "all":
            drop_all(pipe)
        elif mode == "combine":
            drop_product(pipe)
        if mode != "mix":
            eng._params = dict(eng._params, **gains)
        t0 = monotonic_ns()
        pixels, seg = eng._make_frame(shm, i, "image_stream", pipe)
        eng._sync()
        ks.append(seg["filter"] + seg["kernel"])
        if mode == "all" and seg["filter"] <= 0:
            raise SystemExit(f"每帧全重算臂第 {i} 帧没重算——两臂在量同一条路")
        if mode == "combine" and seg["filter"] <= 0:
            raise SystemExit(f"只重组臂第 {i} 帧连重组都没跑：字节没变，缓存键算错了")
        rebands += 1 if mode == "all" and seg["filter"] > 0 else 0
        last = pixels.copy()
    return ks, last, rebands


def part_speed(failures):
    print("\n══ M2-a-2 分层缓存：三档代理 × 三条臂（同轮交替，抗机器热漂移）")
    med = lambda xs: statistics.median(xs)  # noqa: E731
    gains = {"mid_gain": 0.45, "broad_gain": 0.2, "detail_gain": 0.9}
    for budget in BUDGETS:
        d = load_rgb(FIXTURE, budget=budget)
        eng, pipe, shm = new_engine(DEV, d.rgb, d.w, d.h, "spd")
        print(f"── 代理档 {d.w}x{d.h}（{(d.w*d.h*4)/1e6:.2f} MB/帧）")
        try:
            acc = {"all": [], "combine": [], "mix": []}
            lastb = {"all": None, "combine": None, "mix": None}
            for _ in range(REPS):
                for mode in ("all", "combine", "mix"):
                    ks, last, _n = run_arm(eng, pipe, shm, FRAMES, mode, gains)
                    acc[mode].append(med(ks))
                    lastb[mode] = last
            a, b, c = med(acc["all"]), med(acc["combine"]), med(acc["mix"])
            mb = (d.w * d.h * 4) / 1e6          # 每帧 MB（RGBA），与 M1-1 同一个因子
            gain_budget = max(GAIN_BUDGET_MS, GAIN_MS_PER_MB * mb)
            mix_budget = max(MIX_BUDGET_MS, MIX_MS_PER_MB * mb)
            sp = a / max(b, 1e-9)
            pair = [x - y for x, y in zip(acc["all"], acc["combine"])]
            beats = sum(1 for x in pair if x > NOISE_MS)
            print(f"   每帧全重算 {a:.2f} ms → 只重组 {b:.3f} ms（{sp:.1f}x，"
                  f"{beats}/{REPS} 次超噪声底 {NOISE_MS} ms）；只混合 {c:.3f} ms；"
                  f"预算 {gain_budget:.2f}/{mix_budget:.2f} ms")
            print(f"   常驻账单：分带 {pipe.bands_resident_bytes()/2**20:.1f} MiB + "
                  f"成品 {pipe.filter_resident_bytes()/2**20:.1f} MiB")
            if b > gain_budget:
                failures.append(f"{d.w}x{d.h}：只重组每帧 {b:.3f} ms 超预算 {gain_budget:.2f} ms"
                                f"（{mb:.2f} MB/帧）")
            if c > mix_budget:
                failures.append(f"{d.w}x{d.h}：拖强度每帧 {c:.3f} ms 退化（预算 {mix_budget:.2f} ms）")
            if sp < MIN_GAIN_SPEEDUP:
                failures.append(f"{d.w}x{d.h}：分带常驻只带来 {sp:.1f}x，低于 {MIN_GAIN_SPEEDUP}x")
            if beats < REPS:
                failures.append(f"{d.w}x{d.h}：{REPS-beats}/{REPS} 次节省没超过噪声底，省下来的量不可信")
            if not np.array_equal(lastb["all"], lastb["combine"]):
                diff = int(np.abs(lastb["all"].astype(np.int16)
                                  - lastb["combine"].astype(np.int16)).max())
                failures.append(f"{d.w}x{d.h}：只重组臂与每帧全重算臂上屏字节不同（最大 {diff} LSB）")
            else:
                print("   字节对拍：只重组臂与每帧全重算臂逐字节相等 ✓")
        finally:
            shm.close()
            try:
                os.unlink(f"/dev/shm/{shm_name(f'lrt-skin-{os.getpid()}-spd-{d.w}x{d.h}')}")
            except FileNotFoundError:
                pass


# ====================================================== 第三部分：对照图（真图）
def part_reference_images():
    """里程碑验收写的是「磨皮后毛孔细节保留有对照图」——这里把它落成文件。"""
    from PIL import Image

    os.makedirs(OUT_DIR, exist_ok=True)
    d = load_rgb(FIXTURE)                       # 产品默认预算 → 672×848
    x32 = d.rgb.astype(np.float32) / 255.0
    pipe = make_pipeline(DEV, d.w, d.h, d.rgb)

    def shot(gains, strength=1.0):
        drop_all(pipe)
        return pipe.retouch(strength, **gains)[0].cpu().numpy().transpose(1, 2, 0)

    panels = [("1 原图", None),
              ("2 盒式模糊 r=8", "blur"),
              ("3 M2-a 默认 s=1", {}),
              ("4 M2-a tex=0（塑料脸）", {"detail_gain": 0.0})]
    shots = []
    for label, spec in panels:
        if spec is None:
            arr = x32
        elif spec == "blur":
            arr = _box_np(chw(x32), 8)[0].transpose(1, 2, 0)
        else:
            arr = shot(spec)
        shots.append((label, np.clip(arr, 0, 1)))

    # 细带/中带能量用产品算子的带定义量；整幅图的比值只作参考（去斑的证据在回归里）
    print("\n══ M2-a-3 对照图（真图代理档）")
    y0, y1, x0, x1 = 430, 550, 210, 330        # 脸颊皮肤区
    ref_f = None
    tiles = []
    for label, arr in shots:
        c = (arr[y0:y1, x0:x1] * 255).astype(np.uint8)
        tiles.append(np.asarray(Image.fromarray(c).resize(((x1 - x0) * 3, (y1 - y0) * 3),
                                                          Image.NEAREST)))
        f = (arr - _box_np(chw(arr), 4)[0].transpose(1, 2, 0))[y0:y1, x0:x1]
        m = (_box_np(chw(arr), 4) - _box_np(chw(arr), 16))[0].transpose(1, 2, 0)[y0:y1, x0:x1]
        fs, ms = float(f.std()), float(m.std())
        if ref_f is None:
            ref_f = (fs, ms)
        print(f"   {label:22s} 脸颊细带 std={fs:.5f}（×{fs/ref_f[0]:.3f}）"
              f"  中带 std={ms:.5f}（×{ms/ref_f[1]:.3f}）")
    grid = np.concatenate([np.concatenate([t, np.full((t.shape[0], 6, 3), 24, np.uint8)], axis=1)
                           for t in tiles], axis=1)
    cheek = os.path.join(OUT_DIR, "compare-cheek.png")
    Image.fromarray(grid).save(cheek)
    whole = np.concatenate([np.concatenate([np.clip(a, 0, 1), np.full((d.h, 3, 3), 0.1)], axis=1)
                            for _l, a in shots], axis=1)
    fullpng = os.path.join(OUT_DIR, "compare-full.png")
    Image.fromarray((whole * 255).astype(np.uint8)).save(fullpng)
    print(f"   文件：{cheek} ｜ {fullpng}")
    # 这一部分不卡判据：真图上整幅的频带比值被发丝/眼睛/背景边缘占着，本来就看不出磨皮。
    # 它的职责是交付里程碑要的那张对照图；可验证的保留率在第一部分的最小二乘里。


def main() -> int:
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("无 GPU：这份打靶量的是 ROCm 内核与质感保留的产品通路，退出码 2，不给假绿")
        return 2
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    failures: list[str] = []
    print(f"设备={DEV}  重复={REPS}  每次帧数={FRAMES}")
    part_retention(failures)
    part_speed(failures)
    part_reference_images()
    if failures:
        print("\nVERDICT=FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nVERDICT=PASS  （毛孔留住了、色斑去掉了、结构没画圆，而且快的是同一件事）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
