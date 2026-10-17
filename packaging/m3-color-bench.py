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

常驻到底比“每帧重传体积”快多少？**实测只有 1.0×**（三档 0.9–1.0×）：一张 33³ 的表
只有 431 KB，PCIe 上搬一次不到 0.1 ms。所以这里不把“加速比”当判据（那是假指标）：
常驻的真实价值在**热路径上零搬运零分配**，那一条由“N 帧只许一次 to_device”钉住。
对常驻臂只提一个不装样子的要求：它不得比每帧重传更慢（>5% 就说明层里多干了活）。

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
                                        apply_lut_t, parse_cube)
from lumaretouch_engine.quant import quantize_t                     # noqa: E402
from lumaretouch_engine.vram import make_pipeline                   # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
BUDGETS = [int(x) for x in os.environ.get("LRT_BUDGETS", "207360,576000,1310720").split(",")]
REPS = int(os.environ.get("REPS", "5"))
FRAMES = int(os.environ.get("LRT_FRAMES", "40"))
DEV = os.environ.get("LRT_DEVICE", "cuda")

# 每帧 lut 段预算。实测（3×30 帧中位数，产品代理档）：400×504 0.333 ms、
# 672×848 0.587 ms、1024×1280 1.375 ms。这一段含三件事：一次 grid_sample(3d)、
# 一次非有限值归约、一次 synchronize——后者与形变层同构（M2-b 的 deform 段也含它）。
# 口径与形变同一条：按每 MB 源图给，小档留一个下限（一个与尺寸无关的常数会在小档
# 恒真、大档恒假）。2.0 ms/MB 是实测斜率（≈0.35 ms/MB）的 5–6 倍余量，给这么宽是为了
# 不被驱动/时钟漂移误伤，而不是为了“一定绿”。
LUT_BUDGET_MS = 0.6
LUT_MS_PER_MB = 2.0
# 常驻臂相对“每帧重传”的上限。取 1.05 而不是一个好看的加速比：实测两臂在噪声里
# （33³ 表 431 KB，H2D 一次不到 0.1 ms），而“常驻不值钱”这不是靠把判据改成加速比
# 就能变成“值钱”的——真实价值在零搬运零分配，由第二节的 to_device 计数钉住。
MAX_RESIDENT_SLOWER = 1.05


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

    perframe 是"每帧重新上显存"那一臂：它必须与常驻臂**逐字节同结果**（在保真段
    已证），所以这一对比量的纯粹是搬运，不是算法。off 什么表也不挂，是“不开调色
    这一帧多少钱”的基线臂。

    三臂都 pack 一次。上一版只给对照臂加了 pack，于是"常驻快 N 倍"这句话可以从头
    到尾为绿而完全没意义——比的必须是一帧的同一刷工作。
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
        if mode == "resident":
            pipe.render(s)                 # retouch（含链尾调色）+ pack
        elif mode == "perframe":
            # 对照臂：不挂层，每帧把体积重新上一次显存再 apply，然后自己打包
            base = pipe.retouch(s)
            uploads += 1
            out = apply_lut_t(base, cube, vol=cube.to_device(pipe.device))
            pipe.pack(out)
        else:
            pipe.render(s)                 # 基线臂：链尾那个 apply 直接递回原张量
        if DEV.startswith("cuda"):
            torch.cuda.synchronize()
        total += (_t.perf_counter() - c0) * 1000.0
        seg += pipe.last_lut_ms if mode == "resident" else 0.0
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
        res_tot, res_seg, naive_tot, naive_seg, off_tot = [], [], [], [], []
        for rep in range(REPS):
            seq = [lambda: _time_arm(rgb, cube, "resident", FRAMES),
                   lambda: _time_arm(rgb, cube, "perframe", FRAMES),
                   lambda: _time_arm(rgb, cube, "off", FRAMES)]
            if rep % 2:
                seq = [seq[1], seq[0], seq[2]]
            r = seq[0]()
            n = seq[1]()
            o = seq[2]()
            res_tot.append(r[0])
            res_seg.append(r[1])
            naive_tot.append(n[0])
            naive_seg.append(n[1])
            off_tot.append(o[0])
        r_tot = statistics.median(res_tot)
        r_seg = statistics.median(res_seg)
        n_tot = statistics.median(naive_tot)
        o_tot = statistics.median(off_tot)
        budget_ms = max(LUT_BUDGET_MS, LUT_MS_PER_MB * mb)
        slower = r_tot / max(n_tot, 1e-6)
        print(f"  {w}x{h}（{mb:.2f} MB）  不开调色 {o_tot:7.3f}  每帧重传 {n_tot:7.3f}"
              f"  常驻 {r_tot:7.3f}（其中调色段 {r_seg:5.3f}）"
              f"  常驻/重传 {slower:4.2f}×（实测≈1，不拿它当战果）  预算 {budget_ms:.2f} ms")
        if r_seg > budget_ms:
            failures.append(f"{w}x{h} 调色段 {r_seg:.3f} ms 超预算 {budget_ms:.2f} ms")
        if slower > MAX_RESIDENT_SLOWER:
            failures.append(f"{w}x{h} 常驻臂反而比每帧重传慢 {slower:.2f}×，"
                            f"超上限 {MAX_RESIDENT_SLOWER}×：这一层多干了活")
        # 不退化：挂调色的整帧增量必须就是调色段那笔，不能把别的层也拖重算
        if r_tot - o_tot > r_seg + 0.15:
            failures.append(f"{w}x{h} 开调色后整帧多了 {r_tot - o_tot:.3f} ms，"
                            f"比调色段 {r_seg:.3f} ms 多——这一层把别的层也拖重算了")
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
    print("\n" + "=" * 60)
    if failures:
        for f in failures:
            print(f"× {f}")
        print(f"\nVERDICT=FAIL（{len(failures)} 条）")
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
