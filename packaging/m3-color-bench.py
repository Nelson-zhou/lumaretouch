#!/usr/bin/env python3
"""M3 离线打靶：3D LUT 调色到底改没改对颜色、快没快在对地方，不起 GUI。

主张有四句，缺一句都不算成立：

  1) **它算的是标准三线性，不多也不少。** 判据全是目标无关的硬等式：
     · 恒等表 ⇒ 上屏逐字节等于未挂表那一帧（而且 lut_ms 必须为 0，走的是短路不是"算出来恰好一样"）；
     · 强度 0 ⇒ 逐字节还原；
     · 行和为 1、元素非负的跨通道矩阵 ⇒ 与解析真值 **0 LSB**（三线性对线性表数学精确，
       误差只能来自取点/轴序/权重，所以这条比"量个上限"硬得多）；
     · 产品通路（常驻层）与独立臂（直接 apply_lut_t 再打包）⇒ 逐字节相等。
  2) **它不污染别的层。** 挂上表再拖磨皮滑块：滤波零重算、db 零重算、TPS 零重解。
     调色在链尾，它凭什么作废上游缓存？答案必须是"凭不了"。
  3) **"常驻"这两个字是可测的。** N 帧只许一次 H2D。不卡这一条的话，每帧重传在时间上
     只多零点几毫秒，报表看不出来，而语义上它就不是常驻了。
  4) **每帧成本有预算。** 预算按每 MB 源图给（与 m2-face-bench 同一条理由：一个与
     尺寸无关的常数会在小档恒真、大档恒假）。
  5) **内置预设（M3-b）的表复现按资产自己声明的 look_lsb 卡。** 这一轮的表是本仓写的
     解析函数烘的，真值已知，所以"复现到几个 LSB"是个有唯一答案的问题；数字一改判据
     必须同步改——两边都写了出处（gpuspike/m3e.py A 节：33³ 量化最大 2 LSB）。
  6) **肤色定向不进表。** 判据不是"表做不到"而是"表做不准"：同一组参数烘进 33³ 差到
     7–9 LSB / 9–10% 像素，而逐帧内核与 f64 参考差 0–1 LSB 且窗外逐字节不动。banding
     不在这份理由里——m3e 的 D 节沿穿窗口边界的扫描量了两臂跳级都 ≤1，那条假设已证伪。

常驻到底比“每帧重传体积”快多少？**实测省 0.2 ms/帧**（三档 −0.210 / −0.204 / −0.196 ms）：
一张 33³ 的表只有 431 KB，PCIe 上搬一次就是这个量级。所以这里不把“加速比”当判据（0.73–0.93×
这种小数说出来像假指标）：常驻的真实价值在**热路径上零搬运零分配**，那一条由“N 帧只许一次
to_device”钉住。对常驻臂只提一个不装样子的要求：它不得比**走同一条通路的**每帧重传臂多花钱
（绝对值 0.2 ms）。两条臂必须同通路：上一版重传臂是手写 `apply_lut_t` + `pack`，比常驻臂少做了
非有限值归约与一次 synchronize，于是“多花 0.2 ms”量的根本不是搬运；又因为交替写法把**执行
顺序**和**臂身份**绑在一起换了（奇数轮里“常驻”那堆装的是重传臂），两堆互相混样——同一份代码
两次量到 1.03× 与 1.05×、后者当场贴闸红，就是这么来的（本轮被上传计数当场抓包）。比值仍然
打出来，但不当闸。

陡表的烘焙误差在这里**只报数不设阈**：实测说明误差由表的陡峭度决定（33³ 上 gamma 往返的
"轻调"表比 steep 表还差），绝对上限是许愿。真正的上限要由 M3-b 的自研预设自己量出来写进
判据——那一档表是我们自己 bake 的，真值已知。

臂之间交替跑，避免机器热漂移单边占便宜；口径沿用 m1-drag / m2-dnb / m2-face。
"""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_rgb                     # noqa: E402
from lumaretouch_engine.ops.lut import (QUALITY_SIZE_3D, CubeLut,   # noqa: E402
                                        apply_lut_np, apply_lut_t, parse_cube)
from lumaretouch_engine.quant import quantize_t                     # noqa: E402
from lumaretouch_engine.vram import make_pipeline                   # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "5"))
FRAMES = int(os.environ.get("LRT_FRAMES", "40"))
DEV = os.environ.get("LRT_DEVICE", "cuda")

# 每帧 lut 段预算。实测（REPS=5×40 帧中位数，三档）：400×504 0.330 ms、
# 672×848 0.597 ms、1024×1280 1.395 ms。这一段含三件事：一次 grid_sample(3d)、
# 一次非有限值归约、一次 synchronize——后者与形变层同构（M2-b 的 deform 段也含它）。
# 口径与形变同一条：按每 MB 源图给，小档留一个下限（一个与尺寸无关的常数会在小档
# 恒真、大档恒假）。2.0 ms/MB 是实测斜率（≈0.35 ms/MB）的 5–6 倍余量，给这么宽是为了
# 不被驱动/时钟漂移误伤，而不是为了“一定绿”。
LUT_BUDGET_MS = 0.6
LUT_MS_PER_MB = 2.0
# 常驻臂相对“每帧重传”的上限。口径是**走同一条通路的两臂之差**（重传臂每帧多调一次
# set_lut，其余完全同路），实测为负：常驻省 0.196–0.210 ms/帧，恰好是一笔 431 KB 的
# H2D。所以 0.2 ms 这个绝对量不是“鼓个宽闸让它绿”，而是“多花的钱不得超过一次上传的
# 量级”这句话的数值形式。不用比值：两臂物理差别只有一笔固定体积，一个随整帧时长缩放的
# 阈值会在小档恒真、大档压噪声上（上一版 1.05× 就在最大档 1.03↔1.05 之间随机红）。
# 比值仍然打出来，只是不当闸。
MAX_RESIDENT_EXTRA_MS = 0.2
# M3-b：肤色定向段的每帧预算。实测（fixture 三档，REPS=5×40 帧）：0.60 MB 1.090、
# 1.71 MB 1.519、3.93 MB 4.022 ms——斜率约 1.0 ms/MB 再加一笔常数。这里给 2.5 ms/MB
# 与 2.0 ms 下限（小档约 1.8 倍余量，大档约 2.4 倍）。口径与调色段同一条：按每 MB
# 源图给，因为一个与尺寸无关的常数会在小档恒真、大档恒假。
GRADE_BUDGET_MS = 2.0
GRADE_MS_PER_MB = 2.5


def _proxy(budget: int):
    return load_rgb(FIXTURE, budget=budget).rgb


def _cube_text(fn, size: int, *, title: str = "bench") -> str:
    """把一个解析可算的调色函数写成 .cube 文本（blue-varying-first）。

    走文本而不是直接塞数组：产品路径是"用户给一个 .cube 文件"，解析那一步（行序、
    域、越界夹取）也得在这轮里被跑到，否则打靶量的就不是产品通路。
    """
    t = np.linspace(0.0, 1.0, size, dtype=np.float64)
    bb, gg, rr = np.meshgrid(t, t, t, indexing="ij")
    grid = np.stack([rr, gg, bb], axis=-1)                  # (B,G,R,3)
    out = np.clip(np.asarray(fn(grid), dtype=np.float64), 0.0, 1.0)
    rows = out.reshape(-1, 3)
    body = "".join(f"{r:.6f} {g:.6f} {b:.6f}\n" for r, g, b in rows)
    return f'LUT_3D_SIZE {size}\nTITLE "{title}"\n{body}'


def _cube(fn, size: int = QUALITY_SIZE_3D, *, title: str = "bench") -> CubeLut:
    return parse_cube(_cube_text(fn, size, title=title), source=f"{title}.cube")


def linear_matrix(x):
    """行和为 1、元素非负的跨通道矩阵：三线性对它数学精确 ⇒ 判据是 0 LSB。"""
    m = np.array([[0.90, 0.06, 0.04],
                  [0.05, 0.90, 0.05],
                  [0.03, 0.07, 0.90]])
    return x @ m.T


def identity_fn(x):
    return x


def steep_fn(x):
    """只报数不判阈的那张陡表：gamma 往返 + 跨通道矩阵 + 高光压缩。"""
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    lin = np.stack([np.power(r, 2.2), np.power(g, 2.2), np.power(b, 2.2)], axis=-1)
    m = np.array([[1.06, -0.04, -0.02], [-0.03, 1.05, -0.02], [-0.05, -0.03, 1.08]])
    y = lin @ m.T
    hi = y.mean(axis=-1, keepdims=True)
    y = y * (1.0 - 0.18 * np.clip(hi - 0.75, 0.0, None))
    return np.clip(np.power(np.clip(y, 0.0, 1.0), 1.0 / 2.2), 0.0, 1.0)


def _u8(a):
    """LSB 差必须先升 int16：uint8 相减是模 256 回绕的（183−184=255）。"""
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.int16)


def _frame_bytes(pipe, strength: float) -> np.ndarray:
    pipe.render(strength)
    return pipe.read_back()[..., :3].copy()


def _count_uploads(fn):
    """把 CubeLut.to_device 包一层计数器：'常驻' 的唯一可证口径就是它只被调一次。"""
    calls: list = []
    real = CubeLut.to_device

    def spy(self, device):
        calls.append((self.size, str(device)))
        return real(self, device)

    CubeLut.to_device = spy
    try:
        return fn(calls)
    finally:
        CubeLut.to_device = real


# ============================================================ 1) 保真
def part_fidelity(failures: list[str]) -> None:
    print("\n=== 1) 保真：恒等/强度 0/线性表精确/两臂逐字节")
    for budget in BUDGETS:
        rgb = _proxy(budget)
        h, w = rgb.shape[:2]
        pipe = make_pipeline(DEV, w, h, rgb)
        plain = _frame_bytes(pipe, 0.5)
        # 后面三条判据的“解析真值”都必须从 LUT 实际看到的那一份输入算：它是 float32，
        # 而且磨皮（引导滤波）会轻度过冲——实测值域最大到 1.0255。LUT 的定义域是 [0,1]，
        # 超出去的那一点会被夹住（这是表的语义，不是 bug），所以真值也必须先夹同样的域。
        base64 = pipe.retouch(0.5).cpu().numpy()[0].transpose(1, 2, 0).astype(np.float64)
        clipped = np.clip(base64, 0.0, 1.0)
        out_of = float(((base64 < 0.0) | (base64 > 1.0)).mean())

        # ① 恒等表：逐字节不动，而且根本没跑采样
        idc = _cube(identity_fn)
        assert idc.neutral, "恒等文本被判成非恒等：短路失效，下面的判据全成对照"
        pipe.set_lut(idc, 1.0)
        got = _frame_bytes(pipe, 0.5)
        d = int(np.abs(got - plain).max())
        print(f"  {w}x{h} 恒等表：最大 {d} LSB，lut_ms={pipe.last_lut_ms:.3f}")
        if d != 0 or pipe.last_lut_ms != 0.0:
            failures.append(f"{w}x{h} 恒等表差 {d} LSB / lut_ms={pipe.last_lut_ms}"
                            "（不是短路，是算出来恰好一样）")

        # ② 陡表 + 强度 0：逐字节还原
        steep = _cube(steep_fn)
        pipe.set_lut(steep, 0.0)
        got = _frame_bytes(pipe, 0.5)
        d = int(np.abs(got - plain).max())
        if d != 0:
            failures.append(f"{w}x{h} 强度 0 差 {d} LSB：0 不是结构短路")
        print(f"  {w}x{h} 强度 0：最大 {d} LSB")

        # ③ 线性矩阵表：与“先把输入夹进表域、再走那张线性表”的解析真值必须精确复现
        lin = _cube(linear_matrix)
        pipe.set_lut(lin, 1.0)
        got = _frame_bytes(pipe, 0.5)
        truth = linear_matrix(clipped)
        want = _u8(truth)
        d = np.abs(got - want)
        # 唯一的合法例外：float32 算出的值恰好落在量化边界上（…0.5），四舍五入往哪边
        # 取看的是 1e-7 那一位。实测 float32 的绝对误差量级是 2.5e-5 LSB，所以把
        # “离 .5 不足 1e-3 LSB”的子像素排除在外（比实际误差宽 40 倍，不是放水：取点/
        # 轴序/权重错一处会差出整数量级，那些跟边界无关的子像素当场就红）。
        tb = truth * 255.0
        tie = np.abs(tb - np.floor(tb) - 0.5) < 1e-3
        bad = int(d[~tie].max()) if (~tie).any() else 0
        flips = int((d > 0).sum())
        on_tie = int(d[tie].max()) if tie.any() else 0
        print(f"  {w}x{h} 线性表：边界外子像素最大 {bad} LSB（判据 0）；"
              f"总差异 {flips} 个子像素（量化边界候选 {int(tie.sum())}），"
              f"夹域输入 {out_of:.4%}，值域 [{base64.min():.4f}, {base64.max():.4f}]")
        if bad != 0:
            failures.append(f"{w}x{h} 线性表在量化边界之外还差 {bad} LSB："
                            "取点/轴序/权重有一处错了")
        if on_tie > 1:
            failures.append(f"{w}x{h} 连量化边界上的子像素都差了 {on_tie} LSB 以上："
                            "那不是 float32 舍入，是采样本身错了")

        # ④ 产品通路 == 独立臂（挂表走常驻，另一臂直接 apply 再打包）
        pipe.set_lut(steep, 1.0)
        resident = _frame_bytes(pipe, 0.5)
        pipe.clear_lut()
        t = pipe.retouch(0.5)
        pipe.pack(apply_lut_t(t, steep, vol=steep.to_device(pipe.device)))
        solo = pipe.read_back()[..., :3].copy()
        d = int(np.abs(resident - solo).max())
        print(f"  {w}x{h} 常驻臂 vs 独立臂：最大 {d} LSB")
        if d != 0:
            failures.append(f"{w}x{h} 常驻臂与独立臂差 {d} LSB：接线里多了一步数学")

        # ⑤ 陡表烘焙误差：只报数（不设阈，理由见模块头）
        want = _u8(steep_fn(clipped))
        dd = np.abs(resident - want)
        kink = (want <= 0) | (want >= 255)
        print(f"  {w}x{h} 陡表（{QUALITY_SIZE_3D}³）vs 真值：平滑区最大 "
              f"{int(dd[~kink].max())} LSB、全图 {int(dd.max())} LSB、"
              f"改动像素 {(dd > 0).mean():.3%}")
        del pipe


# ============================================================ 2) 零污染 + 只传一次
def part_isolation(failures: list[str]) -> None:
    print("\n=== 2) 挂表后拖滑块：上游一层都不许重算，体积只上一次显存")
    from lumaretouch_engine.ops.deform import analytic_frontal_landmarks
    from lumaretouch_engine.vram import LightOp

    for budget in BUDGETS:
        rgb = _proxy(budget)
        h, w = rgb.shape[:2]
        pipe = make_pipeline(DEV, w, h, rgb)
        pipe.add_light(LightOp(op_id=1, weight=np.full((h, w), 96, np.uint8), sign=1))
        pipe.build_deform(analytic_frontal_landmarks())
        pipe.set_deform_amounts({"slim_face": 0.3, "big_eye": 0.2, "small_chin": 0.1})
        pipe.retouch(0.5)                      # 把上游的重算先付掉（预热）

        def run(calls):
            pipe.set_lut(_cube(steep_fn), 1.0)
            refilter = relight = 0
            builds0 = pipe.deform_builds
            lut_frames = 0
            for i in range(FRAMES):
                s = 0.25 + 0.5 * (i % 100) / 99.0
                pipe.retouch(s)
                if pipe.last_filter_ms > 0.0:
                    refilter += 1
                if pipe.last_light_ms > 0.0:
                    relight += 1
                if pipe.last_lut_ms > 0.0:
                    lut_frames += 1
            return (refilter, relight, pipe.deform_builds - builds0, lut_frames, calls)

        res = _count_uploads(run)
        refilter, relight, builds, lut_frames, calls = res
        print(f"  {w}x{h}  {FRAMES} 帧：重算滤波 {refilter}、重算修容 {relight}、"
              f"重解 TPS {builds}、跑调色 {lut_frames} 帧、上显存 {len(calls)} 次")
        if refilter or relight or builds:
            failures.append(f"{w}x{h} 挂表后拖滑块重算了上游：filter {refilter} / "
                            f"light {relight} / deform_builds {builds}")
        if len(calls) != 1:
            failures.append(f"{w}x{h} {FRAMES} 帧里体积上传 {len(calls)} 次："
                            "常驻没生效（每帧 to_device 就是每帧一次 H2D）")
        if lut_frames != FRAMES:
            failures.append(f"{w}x{h} 只有 {lut_frames}/{FRAMES} 帧真跑了调色："
                            "这一层在报表里存在、在画面里不存在")
        del pipe


# ============================================================ 3) 性能
def _time_arm(rgb, cube, mode: str, frames: int):
    """返回（整帧 ms、lut 段 ms、体积上传次数、常驻字节）。mode 取 resident/perframe/off。

    **两臂走的是同一套层机制，唯一差别是 set_lut 调几次。** 常驻臂在循环前挂一次表，
    重传臂每帧重新 `set_lut` 一次（那笔 to_device 就是“每帧重传”在通路上的唯一体现）。
    上一版重传臂是手写的 `apply_lut_t` + `pack`，它比常驻臂少做了非有限值归约与一次
    synchronize——于是“常驻比每帧重传多花 0.2 ms”这句话量的根本不是搬运，而是两臂
    干的活不一样多（本轮实测就红在 0.200 ms 这个恰好贴闸的位置上）。同一条通路、
    同一刷工作，差值才配叫“常驻这一层多花/省下的钱”。

    off 什么表也不挂，是“不开调色这一帧多少钱”的基线臂。三臂都 pack 一次。上一版
    只给对照臂加了 pack，于是"常驻快 N 倍"这句话可以从头到尾为绿而完全没意义。
    """
    import time as _t

    h, w = rgb.shape[:2]
    pipe = make_pipeline(DEV, w, h, rgb)
    if mode == "resident":
        pipe.set_lut(cube, 1.0)
    total = seg = 0.0
    uploads = 0
    for i in range(frames):
        s = 0.25 + 0.5 * (i % 100) / 99.0
        c0 = _t.perf_counter()
        if mode == "perframe":
            pipe.set_lut(cube, 1.0)        # 每帧重新上一次体积
            uploads += 1
        pipe.render(s)                     # 三臂同一条通路：off 臂链尾直接递回原张量
        if DEV.startswith("cuda"):
            torch.cuda.synchronize()
        total += (_t.perf_counter() - c0) * 1000.0
        seg += pipe.last_lut_ms if mode != "off" else 0.0
    bytes_lut = pipe.lut_resident_bytes()
    del pipe
    return total / frames, seg / frames, uploads, bytes_lut


def part_speed(failures: list[str]) -> None:
    print(f"\n=== 3) 每帧成本（{REPS} 次交替 × {FRAMES} 帧）")
    cube = _cube(steep_fn)
    for budget in BUDGETS:
        rgb = _proxy(budget)
        h, w = rgb.shape[:2]
        mb = h * w * 3 / 1e6
        res_tot, res_seg, nai_tot, nai_seg, off_tot, nai_uploads = [], [], [], [], [], []
        for rep in range(REPS):
            # 交替的是**执行顺序**，不是臂的身份。上一版写成
            # `if rep % 2: seq = [seq[1], seq[0], seq[2]]` 然后 `r = seq[0]()`：奇数
            # 轮里 seq[0] 是重传臂，于是“常驻”那堆样本里混进了重传的、“重传”那堆里混进
            # 了常驻——两堆互相污染到彼此接近，而“常驻比每帧重传多花 0.2 ms”就是在
            # 这种混样上量出来的（本轮当场被上传计数抓包）。
            makers = {"resident": lambda: _time_arm(rgb, cube, "resident", FRAMES),
                      "perframe": lambda: _time_arm(rgb, cube, "perframe", FRAMES),
                      "off": lambda: _time_arm(rgb, cube, "off", FRAMES)}
            order = (["resident", "perframe", "off"] if rep % 2 == 0
                     else ["perframe", "resident", "off"])
            got = {name: makers[name]() for name in order}
            r, n, o = got["resident"], got["perframe"], got["off"]
            res_tot.append(r[0])
            res_seg.append(r[1])
            nai_tot.append(n[0])
            nai_seg.append(n[1])
            nai_uploads.append(n[2])
            off_tot.append(o[0])
        r_tot = statistics.median(res_tot)
        r_seg = statistics.median(res_seg)
        n_tot = statistics.median(nai_tot)
        n_seg = statistics.median(nai_seg)
        o_tot = statistics.median(off_tot)
        # 对照臂必须真在每帧重传，否则这一对比就是“常驻 vs 常驻”——恒为绿而无意义。
        if min(nai_uploads) != FRAMES:
            failures.append(f"{w}x{h} 重传臂 {FRAMES} 帧只上传了 {min(nai_uploads)} 次："
                            "对照臂没对照，下面的搬运对比作废")
        budget_ms = max(LUT_BUDGET_MS, LUT_MS_PER_MB * mb)
        slower = r_tot / max(n_tot, 1e-6)
        extra = r_tot - n_tot
        print(f"  {w}x{h}（{mb:.2f} MB）  不开调色 {o_tot:7.3f}  每帧重传 {n_tot:7.3f}"
              f"（段 {n_seg:5.3f}）  常驻 {r_tot:7.3f}（段 {r_seg:5.3f}）"
              f"  常驻-重传 {extra:+.3f} ms（比值 {slower:4.2f}×，只报数不判阈）  "
              f"预算 {budget_ms:.2f} ms")
        if r_seg > budget_ms:
            failures.append(f"{w}x{h} 调色段 {r_seg:.3f} ms 超预算 {budget_ms:.2f} ms")
        if extra > MAX_RESIDENT_EXTRA_MS:
            failures.append(f"{w}x{h} 常驻臂比同通路每帧重传多花 {extra:.3f} ms，超过一次"
                            f"体积上传的量级（{MAX_RESIDENT_EXTRA_MS} ms）：这一层多干了活")
        # “没把别的层拖重算”由第二节的**直接计数**判（重算滤波/修容/TPS 全 0），不靠减法：
        # 整帧增量比调色段多零点几毫秒，在小档（整帧 0.27 ms）里就是分配器与热噪声的量级，
        # 拿它当闸会在同一份代码上随机红（本轮实测 0.358 与 0.535 两次）。这里只报数。
        print(f"     整帧增量 {r_tot - o_tot:+.3f} ms（调色段 {r_seg:.3f} ms；差值只报数，"
              f"判据见第二节的重算计数）")
        print(f"     显存账单：体积+原件 {cube.size ** 3 * 3 * 4 / 1e6:.3f} MB "
              f"+ {cube.nbytes() / 1e6:.3f} MB（与图尺寸无关，只与表尺寸有关）")


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print("× 缺测试人像，先跑 packaging/make-test-portrait.py")
        return 2
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("× 要跑 GPU 臂但 torch.cuda.is_available()=False")
        return 2
    print(f"设备 {DEV} · torch {torch.__version__} · 档位 {BUDGETS} · "
          f"表 {QUALITY_SIZE_3D}³ · 重复 {REPS} × {FRAMES} 帧")
    failures: list[str] = []
    part_fidelity(failures)
    part_isolation(failures)
    part_speed(failures)
    part_preset(failures)
    part_grade_speed(failures)
    print("\n" + "=" * 60)
    if failures:
        for f in failures:
            print(f"× {f}")
        print(f"\nVERDICT=FAIL（{len(failures)} 条）")
        return 1
    print("VERDICT=PASS")
    return 0


# ============================================================ 4) 内置预设（M3-b）
def part_preset(failures: list[str]) -> None:
    """预设的保真口径：表复现色彩观按**资产自己声明的 look_lsb** 卡，定向按方向卡。

    为什么这里能卡绝对上限而第三节不行：这一轮的表是本仓自己写的解析函数烘出来的，
    真值已知（就是那个函数），所以"复现到几个 LSB"是个能问出唯一答案的问题。
    数字出处：gpuspike/m3e.py A 节（真图 + 全色域 30 万随机点，33³ 量化最大 2 LSB）。
    """
    from lumaretouch_engine.ops import presets as presets_mod
    from lumaretouch_engine.ops.grade import (check_params, grade_np, grade_t, rgb_to_hsv_np,
                                              skin_weight_np)

    print("\n=== 4) 内置预设：表复现、方向、与一键通路")
    rng = np.random.default_rng(20261016)
    gamut = np.concatenate([rng.random((20000, 3)),
                            np.stack(np.meshgrid([0.0, 1.0], [0.0, 1.0], [0.0, 1.0],
                                                 indexing="ij"), -1).reshape(-1, 3)],
                           axis=0).reshape(-1, 1, 3)
    rgb = _proxy(BUDGETS[1])                       # 产品代理档一份就够：这是数值口径不是性能
    x = rgb.astype(np.float64) / 255.0
    w_all = skin_weight_np(rgb_to_hsv_np(np.clip(x, 0.0, 1.0)))
    inside = w_all > 0.5
    for name in presets_mod.names():
        p = presets_mod.get_preset(name)
        cube = presets_mod.preset_lut(p.name)
        # 4a) 表复现色彩观：真图与全色域都按资产声明的上限卡
        for label, sample in (("真图", x), ("全域", gamut)):
            truth = p.look(sample)
            # apply_lut_np 要 (N,3,H,W)：真图与全色域采样都按 (N,1,3) 这条线喂进去
            arr = np.ascontiguousarray(sample.reshape(-1, 1, 3).transpose(2, 0, 1)[None])
            got = apply_lut_np(arr, cube)[0].transpose(1, 2, 0).reshape(sample.shape)
            d = np.abs(_u8(got) - _u8(truth))
            cont = float(np.abs(got - truth).max() * 255.0)
            print(f"  [{p.title}] {label} 表复现：量化 max {int(d.max()):d} LSB（上限 "
                  f"{p.look_lsb}，资产声明）· 连续 max {cont:.3f} LSB · "
                  f"改动 {(d > 0).mean():6.2%}")
            if int(d.max()) > p.look_lsb:
                failures.append(f"{p.title} 的 {label} 表复现差 {int(d.max())} LSB，"
                                f"超资产声明的 {p.look_lsb} LSB：烘表尺寸或色彩观定义变了")
        if cube.clipped:
            failures.append(f"{p.title} 烘出 {cube.clipped} 个越界表值：某一步没夹域")
        if cube.neutral:
            failures.append(f"{p.title} 烘出的是恒等表：色彩观根本没生效")
        # 4b) 定向内核 vs 解析真值 + 窗外逐字节 + 方向
        dh, ds, dv = presets_mod.preset_grade(p.name)
        check_params(dh, ds, dv)                     # 预设自己必须先过硬边界
        ref = grade_np(x, dh, ds, dv)
        t = torch.from_numpy(to_nchw(x).astype(np.float32)).to(DEV)
        got = grade_t(t, dh, ds, dv)[0].permute(1, 2, 0).cpu().numpy().astype(np.float64)
        d = np.abs(_u8(got) - _u8(ref))
        cont = float(np.abs(got - ref).max() * 255.0)
        zero = np.isclose(w_all, 0.0)
        bitexact = bool(np.array_equal(got[zero], np.asarray(x, dtype=np.float32)[zero]))
        hsv0 = rgb_to_hsv_np(np.clip(x, 0.0, 1.0))
        hsv1 = rgb_to_hsv_np(np.clip(got, 0.0, 1.0))
        ds_act = float((hsv1[..., 1] - hsv0[..., 1])[inside].mean())
        dv_act = float((hsv1[..., 2] - hsv0[..., 2])[inside].mean())
        print(f"  [{p.title}] 定向内核：量化 max {int(d.max())} LSB · 连续 max {cont:.2e} LSB ·"
              f" 窗外({zero.mean():.1%})逐位相同={bitexact} · 窗内 Δs {ds_act:+.4f} "
              f"Δv {dv_act:+.4f}（参数 ds={ds:+.3f} dv={dv:+.3f}）")
        if int(d.max()) > 1:
            failures.append(f"{p.title} 的 f32 内核与 f64 参考差 {int(d.max())} LSB")
        if cont > 1e-2:
            failures.append(f"{p.title} 两臂在连续域差 {cont:.2e} LSB：不是精度问题")
        if not bitexact:
            failures.append(f"{p.title} 窗外像素被改了：定向写成了全图调整")
        if ds < 0 and not ds_act < 0:
            failures.append(f"{p.title} 说降饱和（ds={ds}），窗内实测 Δs={ds_act:+.4f}")
        if dv > 0 and not dv_act > 0:
            failures.append(f"{p.title} 说提亮（dv={dv}），窗内实测 Δv={dv_act:+.4f}")
        # 4c) 反向报告（只报数不判阈）：同一组参数烘进表差多少——它就是这层存在的理由
        lut_grade = _cube(lambda q, _p=p: grade_np(q, _p.dh, _p.ds, _p.dv),
                          QUALITY_SIZE_3D, title=f"{name}-grade")
        gt = np.asarray(apply_lut_np(to_nchw(x), lut_grade)[0]).transpose(1, 2, 0)
        dg = np.abs(_u8(gt) - _u8(ref))
        print(f"      反向对照：把定向烘进 33³ 表 → max {int(dg.max())} LSB / 改动 "
              f"{(dg > 0).mean():.2%}（内核 0–1 LSB）← 这一层不能并进表路径")
    # 4d) 一键预设的产品通路：表 + 定向同时上，画面方向与资产一致
    pipe = make_pipeline(DEV, rgb.shape[1], rgb.shape[0], rgb)
    p = presets_mod.get_preset(presets_mod.names()[-1])
    before = _frame_bytes(pipe, 0.5)
    pipe.set_lut(presets_mod.preset_lut(p.name), 1.0)
    pipe.set_grade(*presets_mod.preset_grade(p.name))
    after = _frame_bytes(pipe, 0.5)
    d = after.astype(np.int16) - before.astype(np.int16)
    changed = float((np.abs(d).max(axis=-1) > 0).mean())
    s0 = _sat_u8(before)[w_all > 0.5]
    s1 = _sat_u8(after)[w_all > 0.5]
    print(f"  一键「{p.title}」通路：改动面 {changed:.2%} · 肤色均饱和 "
          f"{s0.mean():.4f}→{s1.mean():.4f} · lut {pipe.last_lut_ms:.3f} ms + "
          f"grade {pipe.last_grade_ms:.3f} ms")
    if changed < 0.5:
        failures.append(f"一键预设只改了 {changed:.2%} 像素：产品通路没把两层都接上")
    if p.ds < 0 and not float(s1.mean()) < float(s0.mean()):
        failures.append(f"一键「{p.title}」后肤色饱和没降（{s0.mean():.4f}→{s1.mean():.4f}）")
    del pipe


def to_nchw(a):
    """(H,W,3) 或 (N,1,3) 的 float64 → (1,3,N,1)：apply_lut_np 的取点约定形状。"""
    arr = np.asarray(a, dtype=np.float64)
    if arr.ndim == 3 and arr.shape[-1] == 3 and arr.shape[1] != 3:
        return np.ascontiguousarray(arr.transpose(2, 0, 1)[None])
    return np.ascontiguousarray(arr.reshape(-1, 1, 3).transpose(2, 0, 1)[None])


def _sat_u8(frame):
    a = np.asarray(frame, dtype=np.float64) / 255.0
    mx = a.max(axis=-1)
    mn = a.min(axis=-1)
    return np.where(mx > 0, (mx - mn) / np.where(mx > 0, mx, 1.0), 0.0)


# ============================================================ 5) 肤色定向的每帧成本（M3-b）
def part_grade_speed(failures: list[str]) -> None:
    """定向是逐帧固定成本（不像滤波有缓存命中），所以它要的是预算与零污染两条。

    实测（产品代理档 928×616，gpuspike/m3e.py F 节）：1.294 ms/帧；全零参数走结构
    短路 0.003 ms。预算按每 MB 给，2.5 ms/MB 加 2.0 ms 下限（本仓 fixture 三档实测
    1.090/1.519/4.022 ms，约 1.0 ms/MB + 常数，所以大档接近 2.4 倍余量）。
    """
    import time as _t

    print(f"\n=== 5) 肤色定向：每帧成本与零污染（{REPS} 次交替 × {FRAMES} 帧）")
    for budget in BUDGETS:
        rgb = _proxy(budget)
        h, w = rgb.shape[:2]
        mb = h * w * 3 / 1e6
        budget_ms = max(GRADE_BUDGET_MS, GRADE_MS_PER_MB * mb)

        def arm(on: bool):
            pipe = make_pipeline(DEV, w, h, rgb)
            if on:
                pipe.set_grade(0.006, -0.14, 0.05)
            for _ in range(5):
                pipe.render(0.5)
            tot = seg = 0.0
            for i in range(FRAMES):
                s = 0.25 + 0.5 * (i % 100) / 99.0
                c0 = _t.perf_counter()
                pipe.render(s)
                if DEV.startswith("cuda"):
                    torch.cuda.synchronize()
                tot += (_t.perf_counter() - c0) * 1000.0
                seg += pipe.last_grade_ms
            del pipe
            return tot / FRAMES, seg / FRAMES

        on_tot, on_seg, off_tot = [], [], []
        for rep in range(REPS):
            # 同上：只换执行顺序，身份跟着结果走
            if rep % 2 == 0:
                on_r, off_r = arm(True), arm(False)
            else:
                off_r, on_r = arm(False), arm(True)
            on_tot.append(on_r[0]); on_seg.append(on_r[1]); off_tot.append(off_r[0])
        o = statistics.median(off_tot)
        g_tot = statistics.median(on_tot)
        g_seg = statistics.median(on_seg)
        print(f"  {w}x{h}（{mb:.2f} MB）  不开定向 {o:7.3f}  开定向 {g_tot:7.3f}"
              f"（其中定向段 {g_seg:5.3f}）  预算 {budget_ms:.2f} ms")
        if g_seg > budget_ms:
            failures.append(f"{w}x{h} 定向段 {g_seg:.3f} ms 超预算 {budget_ms:.2f} ms")
        # 同第三节那条：这一层的“不拖别层重算”由下面那段零污染计数直接判，减法只报数
        print(f"     整帧增量 {g_tot - o:+.3f} ms（定向段 {g_seg:.3f} ms；差值只报数）")
        if g_seg <= 0:
            failures.append(f"{w}x{h} 开了参数而定向段为 0：那一层只存在于上报里")

    # 零污染：挂上定向再拖磨皮滑块，滤波/分带/修容/形变一次都不许重算
    rgb = _proxy(BUDGETS[1])
    h, w = rgb.shape[:2]
    pipe = make_pipeline(DEV, w, h, rgb)
    pipe.prepare()
    first_filter = pipe.last_filter_ms
    pipe.set_grade(0.012, -0.35, 0.28)
    re_seg = 0
    for i in range(FRAMES):
        pipe.render(0.3 + 0.4 * (i % 100) / 99.0)
        if pipe.last_filter_ms > 0 or pipe.last_bands_ms > 0:
            re_seg += 1
    print(f"  零污染：首次滤波 {first_filter:.2f} ms（>0 钉住它真会动）；挂上定向后 "
          f"{FRAMES} 帧里重算 {re_seg} 帧")
    if not first_filter > 0:
        failures.append("首次滤波就是 0：后面那条“不重算”没有对照")
    if re_seg:
        failures.append(f"设了肤色参数却重算了 {re_seg}/{FRAMES} 帧滤波：它被写进了缓存键")
    del pipe


if __name__ == "__main__":
    sys.exit(main())
