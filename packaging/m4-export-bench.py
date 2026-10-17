#!/usr/bin/env python3
"""M4 离线跑靶：全尺寸分块导出——分块 == 整幅、显存峰值只随 tile 走、margin 由参数算。

主张有五句，缺一句都不算成立：

  1) **分块不是另一套实现。** 同一幅尺寸、同一套图层，切块与不切块必须给出同一个
     文件；而 tile=整幅那一次又必须与**产品预览通路**逐字节相等。后半句是关键：
     导出很容易写成"照抄一遍算子调用"，抄错了没人知道，因为两边都能出一张看着对的图。
  2) **0 容差只有一个合法位置**：链上不需要邻域求和的那一组（strength=0 只剩
     逐点层）必须逐字节相等。只要滤波在场就没有 0 容差可讲——积分图 cumsum 的前缀
     随 crop 变，float64 求和顺序随之变，少数像素在量化边界翻面（真图满幅量到
     1 LSB / 3 px）。把这些臂统统写成"0 LSB"，就是拿小靶碰运气恒绿。
  3) **1 LSB 那一笔只允许出现在带滤波的臂上**（磨皮/形变/消除笔）：判据是
     "≤1 LSB 且差异像素占比有界"，不写成"逐字节相等"——后者在这套实现下不真。
  4) **峰值只随 tile 走，不随图幅走。** 这是"防爆显存"唯一的实证口径：同一档 tile
     在 1.28 MP 与 5.2 MP 上的峰值必须同量级，而整幅单 pass 的峰值要按图幅涨。
     立身数据在 `gpuspike/m4a.py`：6000×3968 单 pass 直接 HIP OOM，而 tile512
     在 2150 宽与 6000 宽上是同一个 125.3 MiB。
  5) **margin 是算出来的，不是量出来的。** 逐参数组断言 `margin_px` 等于
     `max(2·rf+6·r, 2·r_db) + ceil(peak|delta|) + 1`，并且**反向门禁**在场：把
     margin 砍半，分块必须当场对不上，而且差异全部关在接缝带里——不然上面那几条
     可以靠"图比作用面小"恒绿。

口径的两处刻意选择：
· **测量用 `max_memory_allocated` 而不是 `reserved`**：后者混进了分配器的缓存与
  复用策略，换一张图就会漂；"一个 tile 峰值要多少"这个问题只有前者的答案。reserved
  一并打印，只当账单。
· **大档是把真图 LANCZOS 放大出来的**。放大只改形状不改语义，而第 4 句判据问的正是
  形状；保真判据（第 1~3 句）全部在**未放大的真 fixture** 上跑。这两件事不能混。

臂之间交替跑，机器热漂移不单边占便宜；口径沿用 m1-drag / m2-face / m3-color。
"""
from __future__ import annotations

import os
import statistics
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_full                    # noqa: E402
from lumaretouch_engine.export import (DEFAULT_TILE, ExportSpec, MAX_TILE,      # noqa: E402
                                        composed_delta, export_image)
from lumaretouch_engine.ops.deform import analytic_frontal_landmarks  # noqa: E402
from lumaretouch_engine.ops.lut import bake                          # noqa: E402
from lumaretouch_engine.vram import (LightOp, PreviewPipeline, RepairOp,        # noqa: E402
                                     make_pipeline)

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEV = os.environ.get("LRT_DEVICE", "cuda")
REPS = int(os.environ.get("REPS", "3"))
BIG_MP = float(os.environ.get("LRT_EXPORT_BIG_MP", "5"))

# 显存预算（tile≤1024，无场臂）。实测（RX 7600 XT，max_memory_allocated）：tile=256 71.9 MiB、
# tile=512 133.6 MiB、tile=1024 319.6 MiB。预算按实测的 ≈ 2 倍给：分块导出的峰值本质是
# "一块采样面积 × 每像素的 float64 中间量"，换卡/换驱动会漂，但不会漂一个数量级。
MEM_BUDGET = {"256": 160.0, "512": 280.0, "1024": 680.0}
# 同一档 tile 在两种图幅上的允许差。峰值里随图幅涨的部分应当是 0：形变场落回 CPU
# （那是 RAM）、消除笔按洞的 bbox 满幅预跑，两者在 GPU 侧的份额都按带/按 bbox 定。
MEM_SPAN_TOL_MIB = float(os.environ.get("LRT_EXPORT_MEM_SPAN_MIB", "24"))
# 带场臂的预算（tile=512）。除了 tile 的采样面积，还多一笔按行的场求值（1<<15 px）
MEM_BUDGET_DEFORM_MIB = float(os.environ.get("LRT_EXPORT_MEM_DEFORM_MIB", "320"))
# 吞吐预算，按每百万像素给。出片是批量的：一分钟能不能吃完一组两百张，看的是这个。
# 两臂分开给：形变那一笔是 float64 的 TPS 稠密求值（三个语义层×每层≈ 33–48 ms/MP，
# RDNA3 的 FP64 是 1/32 速率），把它算进"磨皮+色彩"的预算里只会逼出一个两边都不真的
# 中间值。实测写在下面的注释里，改实现必须同时改这两个数。
MS_PER_MP_PLAIN = float(os.environ.get("LRT_EXPORT_MS_PER_MP", "120"))
MS_PER_MP_DEFORM = float(os.environ.get("LRT_EXPORT_MS_PER_MP_DEFORM", "260"))


def _need_env() -> None:
    if not os.path.isfile(FIXTURE):
        print(f"缺 fixture：{FIXTURE}（先跑 packaging/make-test-portrait.py）")
        sys.exit(2)


def full_src() -> np.ndarray:
    return load_full(FIXTURE).rgb


def big_src(rgb: np.ndarray) -> np.ndarray:
    """把真图放大到 BIG_MP 万像素——只为把**形状**推到真实出片量级。

    判据第 4 句问的是"峰值随什么走"，那是形状问题。保真判据一条都不在这里跑。
    """
    from PIL import Image
    h, w = rgb.shape[:2]
    k = float(np.sqrt(BIG_MP * 1e6 / float(h * w)))
    nh, nw = int(round(h * k)), int(round(w * k))
    with Image.fromarray(rgb) as im:
        return np.ascontiguousarray(np.asarray(im.resize((nw, nh), Image.LANCZOS), np.uint8))


def cube():
    return bake(lambda x: np.clip(x @ np.array([[0.94, 0.04, 0.02],
                                                [0.03, 0.93, 0.04],
                                                [0.05, 0.06, 0.89]]).T, 0.0, 1.0),
                33, title="m4-export-bench")


def blob(h: int, w: int, cy: float, cx: float, rad: float, value: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    wt = np.zeros((h, w), np.uint8)
    wt[np.hypot(xx - w * cx, yy - h * cy) < min(w, h) * rad] = value
    return wt


def layers(h: int, w: int, *, light=True, repair=False, deform=False, color=True):
    """按导出尺寸造一套图层。返回 (kw, lm, delta_peak)。"""
    lm = analytic_frontal_landmarks() if deform else None
    kw = {}
    if light:
        kw["light"] = [LightOp(op_id=1, weight=blob(h, w, 0.42, 0.5, 0.16, 110), sign=-1)]
    if repair:
        kw["repair"] = [RepairOp(op_id=1, weight=blob(h, w, 0.62, 0.30, 0.05, 255))]
    if deform:
        kw["deform_amounts"] = {"slim_face": 0.5, "big_eye": 0.3, "small_chin": 0.2}
        kw["landmarks"] = lm
    if color:
        kw["cube"] = cube()
        kw["grade"] = (0.006, -0.14, 0.05, 1.0)
    return kw


def lsb(a, b):
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=-1)
    return int(d.max()), d


def seam_split(diff_mask, h: int, w: int, tile: int, near: int = 1, gap: int = 0):
    """把差异像素按“离网格线多远”分成三堆。

    两个开口方向各自对应一个不同的错：“差异全贴在缝上”是 margin 不够，
    “缝外还有差异”则不是接缝（而是网格接错了）。单靠一个比例量不出这两件事。
    返回 (贴缝的, 离缝的, 离缝超过 gap 的)。
    """
    bxs = [x for x in range(tile, w, tile)]
    bys = [y for y in range(tile, h, tile)]
    yy, xx = np.mgrid[0:h, 0:w]
    dx = np.min(np.stack([np.abs(xx - x) for x in bxs]), axis=0) if bxs else np.full((h, w), 1e9)
    dy = np.min(np.stack([np.abs(yy - y) for y in bys]), axis=0) if bys else np.full((h, w), 1e9)
    on = (dx <= near) | (dy <= near)
    far = (dx > gap) & (dy > gap)
    hit = diff_mask > 0
    return int(hit[on].sum()), int(hit[~on].sum()), int(hit[far].sum())


# ------------------------------------------------------------------ 1/2/3 保真
def part_fidelity(failures: list[str]) -> None:
    print("\n=== 1) 分块 == 整幅（真 fixture 满幅，未放大） ===")
    rgb = full_src()
    h, w = rgb.shape[:2]
    mb = h * w * 3 / 1e6
    print(f"  靶：{w}x{h}（{mb:.2f} MB / {h * w / 1e6:.2f} MP），tile 下界 {256}")

    def spec_of(**kw):
        base = dict(strength=0.6, radius=12, eps=6e-4, texture_radius=4,
                    detail_gain=1.0, mid_gain=0.0, broad_gain=0.0)
        base.update(kw)
        return ExportSpec(**base)

    arms = [
        # 0 容差只有一个合法位置：链上不需要邻域求和的那一组（strength=0 短路滤波）
        ("逐点（strength=0 + 色彩）", spec_of(strength=0.0, **layers(h, w, light=False)), 0, 0.0),
        ("磨皮+修容+色彩（无形变）", spec_of(**layers(h, w)), 1, 0.00005),
        ("只磨皮", spec_of(**layers(h, w, light=False, color=False)), 1, 0.00005),
        ("+形变", spec_of(**layers(h, w, deform=True)), 1, 0.001),
        ("+消除笔", spec_of(**layers(h, w, light=False, repair=True)), 1, 0.0005),
    ]
    for tag, s, lsb_cap, px_cap in arms:
        one, st_one = export_image(rgb, s, device=DEV, tile=MAX_TILE)
        assert st_one["tiles"] == 1, "MAX_TILE 没能覆盖整幅，这一臂的对照就没了"
        line = f"  {tag:22s} margin={st_one['margin_px']:4d}  "
        worst = 0
        for tile in (256, 512, 1024):
            got, st = export_image(rgb, s, device=DEV, tile=tile)
            d, mask = lsb(got, one)
            n_on, n_off, _far = seam_split(mask, h, w, tile, near=1)
            frac = float((mask > 0).mean())
            worst = max(worst, d)
            line += f"t{tile} {d}LSB/{frac:6.4%}  "
            if d > lsb_cap:
                failures.append(f"{tag} tile={tile} 与整幅差 {d} LSB（上限 {lsb_cap}）："
                                "margin 不够，或某层根本不是局部的")
            if frac > px_cap:
                failures.append(f"{tag} tile={tile} 差异像素 {frac:.4%} 超上限 {px_cap:.4%}")
            if lsb_cap and d > 0 and st["tiles"] > 1 and n_off == 0 and n_on > 4:
                # 1 LSB 那一笔的来源是求和顺序，它不偏爱网格线：差异全贴在缝上就是真接缝
                failures.append(f"{tag} tile={tile} 的 {n_on} 个差异全部贴在网格线上："
                                "那不是舍入，是 margin 不够")
        print(line + f"（最坏 {worst} LSB，判据 ≤{lsb_cap}）")

    print("\n=== 2) 导出 == 产品预览通路（同一实现，不是抄一遍） ===")
    s = arms[3][1]
    # 参考：预览通路在同尺寸上跑一帧
    pipe = make_pipeline(DEV, w, h, rgb)
    if s.light:
        pipe.set_light_ops(list(s.light))
        pipe.set_light_params(s.light_exposure, s.light_radius)
    delta, peak = composed_delta(s.landmarks, s.deform_amounts, h, w, DEV)
    pipe.adopt_deform_field(delta.to(DEV))
    pipe.set_lut(s.cube, s.lut_amount)
    pipe.set_grade(*s.grade[:3], amount=s.grade[3])
    pipe.render(s.strength, radius=s.radius, eps=s.eps, detail_gain=s.detail_gain,
                mid_gain=s.mid_gain, broad_gain=s.broad_gain,
                texture_radius=s.texture_radius)
    ref = pipe.read_back()[..., :3].copy()
    del pipe, delta
    one, _st = export_image(rgb, s, device=DEV, tile=MAX_TILE)
    d, mask = lsb(one, ref)
    print(f"  整幅导出 vs 预览通路（{w}x{h}，含形变场）：max {d} LSB / "
          f"{int((mask > 0).sum())} px（peak 位移 {peak:.1f} px）")
    if d > 1:
        failures.append(f"导出与预览通路差 {d} LSB：导出用的是另一套实现或漏了一层")
    elif d == 1:
        # 允许 1 LSB 只有一种解释：预览那一路把整幅当一块跑，而导出 tile=整幅 时
        # margin 被夹在图像边界上——同一像素的两套边界读取。数字必须极小。
        if float((mask > 0).mean()) > 0.0005:
            failures.append(f"导出 vs 预览差 1 LSB 却铺了 {float((mask > 0).mean()):.3%} 像素")

    print("\n=== 3) 什么都没开 = 解码原图逐字节（满幅通路也要守这条） ===")
    s0 = ExportSpec(strength=0.0, light=[], repair=[], deform_amounts={}, cube=None,
                    grade=(0.0, 0.0, 0.0, 1.0))
    for tile in (256, 1024):
        out, st = export_image(rgb, s0, device=DEV, tile=tile)
        same = np.array_equal(out, rgb)
        print(f"  tile={tile}（{st['tiles']} 块）逐字节相等：{same}")
        if not same:
            failures.append(f"strength=0 无图层 tile={tile} 出的不是原图：那一档根本没短路")


# ------------------------------------------------------------------ 4 margin
class _ShrunkSpec(ExportSpec):
    """把 margin 按系数砍掉。反向门禁专用，不改生产代码里的公式。"""

    def __init__(self, *a, factor=0.5, **kw):
        super().__init__(*a, **kw)
        self._factor = factor

    def margin_px(self, deform_peak_px: float = 0.0) -> int:
        return int(super().margin_px(deform_peak_px) * self._factor)


def part_margin(failures: list[str]) -> None:
    print("\n=== 4) margin 由参数算：逐组定点 + 砍半必红 ===")
    rgb = full_src()
    h, w = rgb.shape[:2]
    cases = [
        ("r=12 rf=4 无笔", dict(radius=12, texture_radius=4, light=[]), 80),
        ("r=24 rf=6 无笔", dict(radius=24, texture_radius=6, light=[]), 156),
        ("r=6 rf=2 无笔", dict(radius=6, texture_radius=2, light=[]), 40),
        ("r=4 rf=2 + 修容 24", dict(radius=4, texture_radius=2,
                                    light=layers(h, w)["light"], light_radius=24), 48),
        ("r=20 rf=4 + 修容 24", dict(radius=20, texture_radius=4,
                                     light=layers(h, w)["light"], light_radius=24), 128),
    ]
    for tag, kw, want in cases:
        base = dict(strength=0.5, eps=6e-4)
        base.update(kw)
        s = ExportSpec(**base)
        one, st = export_image(rgb, s, device=DEV, tile=512)
        print(f"  {tag:22s} margin={st['margin_px']:4d}（期望 {want}）  "
              f"{st['tiles']} 块")
        if st["margin_px"] != want:
            failures.append(f"{tag} margin={st['margin_px']} != 公式 {want}")
        if st["margin_px"] > MAX_TILE:
            failures.append(f"{tag} 的 margin 比 tile 还大，有效区是负的")
    # 形变那一笔：+ceil(peak)+1，且必须真的随参数变
    s = ExportSpec(strength=0.6, radius=8, texture_radius=3, light=[],
                   **layers(h, w, light=False, color=False, deform=True))
    got, st = export_image(rgb, s, device=DEV, tile=512)
    want = 2 * 3 + 6 * 8 + int(np.ceil(st["deform_peak_px"])) + 1
    print(f"  形变那一笔            margin={st['margin_px']:4d}（期望 {want}，"
          f"peak={st['deform_peak_px']} px）")
    if st["margin_px"] != want:
        failures.append(f"形变项没按 ceil(peak)+1 加：{st['margin_px']} != {want}")

    print("  反向门禁：margin 砍半，分块必须当场对不上，且差异全贴在缝上")
    base_kw = dict(strength=0.6, radius=12, texture_radius=4,
                   light=layers(h, w)["light"], light_radius=24)
    one, _st = export_image(rgb, ExportSpec(**base_kw), device=DEV, tile=MAX_TILE)
    ok, _st_ok = export_image(rgb, ExportSpec(**base_kw), device=DEV, tile=512)
    base_px = int((lsb(ok, one)[1] > 0).sum())
    print(f"    基线（margin 足）tile=512 差异 {base_px} px")
    for tile, factor in ((512, 0.5), (512, 0.125)):
        s2 = _ShrunkSpec(**base_kw, factor=factor)
        two, st = export_image(rgb, s2, device=DEV, tile=tile)
        d, mask = lsb(one, two)
        count = int((mask > 0).sum())
        # “贴缝”的空间口径：缺口 = 真 margin − 实 margin；离任何缝超过缺口的区域必须零差异
        real = ExportSpec(**base_kw).margin_px()
        gap = real - st["margin_px"]
        n_on, n_off, n_far = seam_split(mask, h, w, tile, near=gap, gap=gap)
        print(f"    factor={factor:<6} margin={st['margin_px']:3d}（真 {real} 缺口 {gap}）  "
              f"max {d} LSB / {count:7d} px（基线 {base_px}）/ 贴缝 {n_on} / 缝外 {n_far}")
        if count < max(200, base_px * 100):
            failures.append(f"margin 砍到 {st['margin_px']} 只有 {count} px 对不上"
                            f"（基线 {base_px}）：这张靶没有作用面，上面的对拍不算证伪")
        if factor <= 0.125 and d < 2:
            failures.append(f"margin 砍到八分之一仍只差 {d} LSB：接缝没被量到")
        if n_far:
            failures.append(f"缝外还有 {n_far} 个差异像素：那不是 margin 不够，是另一件事")
        if n_off and n_on == 0:
            failures.append(f"{n_off} 个差异全在缺口带之外：它们不该受这次 margin 影响")


# ------------------------------------------------------------------ 5 显存账
def peak_mib(fn, *a, **kw):
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    out = fn(*a, **kw)
    torch.cuda.synchronize()
    alloc = torch.cuda.max_memory_allocated() / 2**20
    resv = torch.cuda.max_memory_reserved() / 2**20
    return out, alloc, resv


def part_memory(failures: list[str]) -> None:
    print("\n=== 5) 峰值只随 tile 走，不随图幅走 ===")
    if not torch.cuda.is_available():
        print("  没得测：显存峰值在 CPU 上没有对应量，不拿它装 PASS")
        return
    rgb = full_src()
    sh, sw = rgb.shape[:2]
    big = big_src(rgb)
    bh, bw = big.shape[:2]
    print(f"  两幅靶：{sw}x{sh}（{sh * sw / 1e6:.2f} MP） / {bw}x{bh}（{bh * bw / 1e6:.2f} MP，"
          f"放大件只为形状）")

    def run(arr, tile, *, deform):
        h, w = arr.shape[:2]
        s = ExportSpec(strength=0.6, radius=12, texture_radius=4,
                      **layers(h, w, deform=deform))
        (_o, st), a, r = peak_mib(export_image, arr, s, device=DEV, tile=tile)
        m = st["margin_px"]
        crop = (min(tile + 2 * m, w), min(tile + 2 * m, h))
        return a, r, st, crop[0] * crop[1]

    print("  严格对照（无场臂：margin 只由半径定，两幅图的采样面积完全同构）")
    table = {}
    for tile in (256, 512, 1024, MAX_TILE):
        a1, r1, st1, c1 = run(rgb, tile, deform=False)
        a2, r2, st2, c2 = run(big, tile, deform=False)
        table[tile] = (a1, a2, st1, st2, c1, c2)
        fits = min(sw, sh) >= tile + 2 * st1["margin_px"]
        print(f"  tile={tile:5d}  小块 {a1:7.1f} MiB（{st1['tiles']:3d} 块）  "
              f"大块 {a2:7.1f} MiB（{st2['tiles']:3d} 块）  图幅比 {a2 / max(a1, .1):5.2f}  "
              f"采样 {(c1 + c2) / 2 / 1e6:.04f} MP  {'全块能放下' if fits else '图太窄，夹边'}  "
              f"reserved {r1:5.0f}/{r2:5.0f}")
        budget = MEM_BUDGET.get(str(tile))
        if budget and tile != MAX_TILE and a2 > budget:
            failures.append(f"tile={tile} 峰值 {a2:.1f} MiB 超预算 {budget:.0f} MiB")
    # 立身判据：同一档 tile + 同一档 margin，图幅翻 3.8 倍而峰值不动
    for tile in (256, 512, 1024):
        a1, a2, _s1, _s2, c1, c2 = table[tile]
        if abs(c1 - c2) > 0.02 * max(c1, c2):      # 采样面积不同构就不是同一个对照
            print(f"    tile={tile} 两幅图的采样面积不同（{c1 / 1e6:.3f} vs {c2 / 1e6:.3f} MP）："
                  "这一档不进严格对照，只报数")
            continue
        if abs(a2 - a1) > MEM_SPAN_TOL_MIB:
            failures.append(f"tile={tile} 在两幅图上峰值差 {abs(a2 - a1):.1f} MiB"
                            f"（容差 {MEM_SPAN_TOL_MIB:.0f}，采样面积同为 {c1 / 1e6:.3f} MP）："
                            "峰值在随图幅走，那不是分块")
    a_small_single = table[MAX_TILE][0]
    a_big_single = table[MAX_TILE][1]
    ratio_mp = (bh * bw) / (sh * sw)
    print(f"  整幅单 pass 随图幅涨：{a_small_single:.1f} → {a_big_single:.1f} MiB "
          f"（像素比 {ratio_mp:.2f}×）")
    if a_big_single < a_small_single * min(ratio_mp, 1.5):
        failures.append("整幅单 pass 的峰值没随图幅涨：这张卡或这套层根本没被撑起来")
    saved = a_big_single / max(table[512][1], 0.1)
    print(f"  分块省下的倍数（大幅 tile512 vs 整幅）：{saved:.1f}×")
    if saved < 3.0:
        failures.append(f"tile=512 只比整幅省 {saved:.1f}×：分块在这套参数下没意义")
    # 带场臂：margin 里那一笔 ceil(peak)+1 本身按像素计，而脸越大位移越大
    print("  带场臂（只报数，不当严格对照）：")
    for tile in (512, MAX_TILE):
        a1, _r1, st1, c1 = run(rgb, tile, deform=True)
        a2, _r2, st2, c2 = run(big, tile, deform=True)
        print(f"    tile={tile:5d}  {a1:7.1f} → {a2:7.1f} MiB（margin {st1['margin_px']} → "
              f"{st2['margin_px']}，peak {st1['deform_peak_px']} → {st2['deform_peak_px']} px，"
              f"采样 {c1 / 1e6:.3f} → {c2 / 1e6:.3f} MP，场占 RAM {st2['delta_cpu_mb']} MiB）")
        if tile != MAX_TILE and a2 > MEM_BUDGET_DEFORM_MIB:
            failures.append(f"带场臂 tile={tile} 峰值 {a2:.1f} MiB 超预算 "
                            f"{MEM_BUDGET_DEFORM_MIB:.0f} MiB")
        if st2["margin_px"] > st1["margin_px"] and a2 > a1 * (c2 / max(c1, 1)) * 1.4:
            failures.append(f"带场臂峰值涨得比采样面积还快（{a1:.1f}→{a2:.1f} MiB / "
                            f"{c1 / 1e6:.3f}→{c2 / 1e6:.3f} MP）：场那一笔没被按带按住")


# ------------------------------------------------------------------ 6 吞吐
def part_speed(failures: list[str]) -> None:
    print(f"\n=== 6) 出片吞吐（产品档 tile={DEFAULT_TILE}） ===")
    big = big_src(full_src())
    bh, bw = big.shape[:2]
    mp = bh * bw / 1e6
    for tag, deform, budget in (("磨皮+修容+色彩（无场）", False, MS_PER_MP_PLAIN),
                                ("上面 + 形变", True, MS_PER_MP_DEFORM)):
        s = ExportSpec(strength=0.6, radius=12, texture_radius=4, **layers(bh, bw, deform=deform))
        per: list[float] = []
        st = None
        for rep in range(REPS):
            t0 = time.perf_counter()
            _out, st = export_image(big, s, device=DEV, tile=DEFAULT_TILE)
            ms = (time.perf_counter() - t0) * 1000.0
            per.append(ms / mp)
            print(f"  {tag} #{rep}  {ms:8.1f} ms = {ms / mp:6.1f} ms/MP  "
                  f"（{st['tiles']} 块 / 每块 {st['per_tile_ms']} ms / 场 {st['field_ms']} ms）")
        med = statistics.median(per)
        # 账单要能解释得了大头：五个算子段 + 三段搬运 + 那一次整幅场求值
        accounted = sum(st["seg_ms"].values()) / mp + st["field_ms"] / mp
        print(f"  {tag} 中位 {med:.1f} ms/MP（预算 {budget:.0f}）；已归因 {accounted:.1f} ms/MP："
              + " ".join(f"{k} {v / mp:.1f}" for k, v in st["seg_ms"].items()))
        if med > budget:
            failures.append(f"{tag} {med:.1f} ms/MP 超预算 {budget:.0f} ms/MP")
        if accounted < med * 0.7:
            failures.append(f"{tag} 已归因只占 {accounted / med:.0%}：那笔时间不知道去哪了")
        for k in ("filter", "lut"):
            if st["seg_ms"][k] <= 0:
                failures.append(f"{tag} 的 {k} 段为 0：挂着这一层跑的靶不成立")


# ------------------------------------------------------------------ 7 零污染
def part_isolation(failures: list[str]) -> None:
    print("\n=== 7) 导出不弄脏预览会话（同卡不同尺寸，缓存键不许被串） ===")
    rgb = full_src()
    h, w = rgb.shape[:2]
    pw, ph = 640, 800
    from PIL import Image
    proxy = np.ascontiguousarray(np.asarray(Image.fromarray(rgb).resize((pw, ph),
                                                                       Image.LANCZOS), np.uint8))
    pipe = make_pipeline(DEV, pw, ph, proxy)
    pipe.set_grade(0.012, -0.35, 0.28)
    first = pipe.render(0.45)
    base = pipe.read_back()[..., :3].copy()
    f0 = pipe.last_filter_ms
    # 满幅导出：另一套尺寸、另一批图层对象
    s = ExportSpec(strength=0.6, radius=12, texture_radius=4, **layers(h, w, deform=True))
    export_image(rgb, s, device=DEV, tile=512)
    again = pipe.render(0.45)
    after = pipe.read_back()[..., :3].copy()
    del first, again
    same = np.array_equal(base, after)
    print(f"  导出前滤波段 {f0:.2f} ms（>0 钉住它真算过）；导出后再渲染逐字节一致：{same}，"
          f"重算滤波 {pipe.last_filter_ms:.3f} ms")
    if not f0 > 0:
        failures.append("导出前那次滤波根本没算：后面那条“没被重算”没有对照")
    if not same:
        failures.append("满幅导出之后预览画面变了：两条通路共享了不该共享的东西")
    if pipe.last_filter_ms > 0:
        failures.append("满幅导出把预览的滤波缓存作废了：会话键被串")


def main() -> int:
    _need_env()
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("没有可用的 ROCm/CUDA 设备（LRT_DEVICE=cuda）。显存与吞吐判据在 CPU 上没有意义，"
              "本跑靶拒绝在 CPU 上自证。")
        return 2
    failures: list[str] = []
    part_fidelity(failures)
    part_margin(failures)
    part_memory(failures)
    part_speed(failures)
    part_isolation(failures)
    print()
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print(f"\nVERDICT=FAIL（{len(failures)} 条）")
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
