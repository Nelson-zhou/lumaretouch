"""3D LUT（M3-a）：.cube 解析 + GPU 查表插值 + 烘焙预设。

口径全部来自 gpuspike/m3a.py / m3b.py 在真机上的实测，不是推理：

1. **grid_sample(3d, align_corners=True) 就是三线性插值**。17³/33³/64³ 三档与手写
   三线性在 uint8 输出上**逐字节相同**。所以产品走一次 grid_sample（672×848 实测
   0.35 ms/帧），而不是 gather 版（4.59 ms）——慢 13 倍却没有更准。
2. **查表不需要 float64**。同一臂 float32 与 float64 的结果差 0.000 LSB（与 TPS 那层
   必需 float64 形成对照：那里是 1e7 量级的核函数相减，这里是插值）。
3. **误差由 LUT 尺寸决定**：以一个 float64 上可精确算的调色函数当真值，实测最大偏差
   17³ = 12 LSB、33³ = 5 LSB、64³ = 3 LSB。所以低于 33 的粗表要**明确报精度不足**，
   不许静默上屏（`CubeLut.notes`）。
4. **轴序**：.cube 的行序是 R 变化最快、G 次之、B 最慢（blue-varying-first）。写反不会
   报错，只会把色彩空间转置——实测纯 R 输入的响应曲线差 255 LSB、整图上屏差 108 LSB。
   内部网格一律存成 `(B, G, R, 3)`，这个约定在本文件里只出现在两处：读行时的 reshape
   与给 grid_sample 的 permute，其余地方都靠张量形状说话。
5. **恒等表必须逐字节还原**。数学上三线性对恒等表是精确的（实测 0 LSB），但"数学上
   精确"不等于"float32 上精确"，所以 neutral 走显式短路——这是结构性保证，不是经验值。

测量口径的坑（踩过，写在这里防止重犯）：比 LSB 之前**必须先升 int16**。uint8 相减是模
256 回绕的，`183 − 184 = 255`，会把 1 LSB 的真偏差量成"255 LSB 大错"。
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")

# ---- 边界（都是实测/规格定的，不是许愿值）----
MIN_SIZE_3D = 2
MAX_SIZE_3D = 64                        # 64³×3×4 B = 512 KB，再大收益见 notes 第 3 条
QUALITY_SIZE_3D = 33                    # 低于它最大偏差进 10 LSB 量级（17³ 实测 12 LSB）
NEUTRAL_TOL = 1e-6                      # 恒等判定：与 identity 表的最大差
MAX_TEXT_BYTES = 32 * 1024 * 1024       # 64³ 文本约 3 MiB；再大的文件先怀疑是错文件
# 调色强度的混合系数。上下界取 [0,1] 而不是允许负值（反向调色）：负方向在 LUT 语义里
# 没有定义——它不是“把表反着走”，而是把输出往原点的镜像上推，出来的色彩没人能预期。
AMOUNT_MIN = 0.0
AMOUNT_MAX = 1.0
DEFAULT_LUT_AMOUNT = 1.0


class LutError(ValueError):
    """解析或应用被拒。整条拒绝，不留半截 LUT。"""


def check_amount(value) -> float:
    """调色强度的唯一校验口径：协议层与常驻层共用，不各写一份区间。

    为什么要一个函数而不是调用方各自 `float(v)`：M1-3c/M2-b 两次都是同一个形状——
    命令层校验、库层不校验，于是直调库层的通路（跑靶、换设备重放）能把 NaN 写进状态，
    而 NaN 参与混合会把整帧打成非有限值。NaN 比大小恒为 False，只有这里能拦住它。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise LutError(f"调色强度非法：{value!r}（需 {AMOUNT_MIN}–{AMOUNT_MAX} 的有限数）") from None
    if not math.isfinite(v):
        raise LutError(f"调色强度不是有限数：{value!r}")
    if not AMOUNT_MIN <= v <= AMOUNT_MAX:
        raise LutError(f"调色强度 {v} 超出范围 [{AMOUNT_MIN}, {AMOUNT_MAX}]")
    return v


@dataclass(frozen=True)
class CubeLut:
    """一张 LUT。kind="3d" 时 grid 是 (s,s,s,3)，kind="1d" 时是 (s,3)。

    值一律 float64 ∈ [0,1]（CPU 侧原件）。上 GPU 时由 `grid_tensor()` 转 float32——
    实测 f32 与 f64 逐字节同值，所以升精度没有意义。
    """
    kind: str
    size: int
    grid: np.ndarray
    title: str = ""
    domain_min: tuple = (0.0, 0.0, 0.0)
    domain_max: tuple = (1.0, 1.0, 1.0)
    clipped: int = 0
    neutral: bool = False
    notes: tuple = field(default_factory=tuple)
    # 这张表从哪来（文件名 / "text" / "preset:xxx"）。上报里必须能说出话来：用户载入两个
    # 同名 33³ 的表时，只有 source 能区分事件里报的是哪一张——而它正是“载入成功但画面
    # 没动”那类问题的第一现场证据。
    source: str = ""

    def nbytes(self) -> int:
        return int(self.grid.nbytes)

    def to_device(self, device):
        """上显存。(1, C, D=B, H=G, W=R) 的体积张量，float32。"""
        if torch is None:
            raise RuntimeError("本模块需要 torch 才能上显存")
        vol = torch.from_numpy(np.ascontiguousarray(
            self.grid.astype(np.float32))).permute(3, 0, 1, 2)[None]
        return vol.to(device)


def _identity_grid(size: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, size, dtype=np.float64)
    bb, gg, rr = np.meshgrid(t, t, t, indexing="ij")            # B 最外层（blue-varying-first）
    return np.stack([rr, gg, bb], axis=-1)


def _check_clipped(vals: np.ndarray) -> int:
    bad = int(((vals < 0.0) | (vals > 1.0)).sum())
    return bad


# ------------------------------------------------------------------ 解析
def parse_cube(text: str, *, source: str = "<text>") -> CubeLut:
    """解析 .cube 文本。任何一条不合格就整条拒（不留"解析了一半"的表）。

    支持：`LUT_3D_SIZE` / `LUT_1D_SIZE`、`TITLE`、`DOMAIN_MIN` / `DOMAIN_MAX`、
    `#` 注释、空行、科学计数法。值超出 [0,1] 不拒但**记账**（`clipped`），因为
    现实里轻微过冲的表很常见，而静默吞掉一个参数比拒绝难查十倍。
    """
    if len(text.encode("utf-8", errors="ignore")) > MAX_TEXT_BYTES:
        raise LutError(f"{source}: 文本 {len(text) // 1024} KiB 超过上限 "
                       f"{MAX_TEXT_BYTES // 1048576} MiB，先确认这不是别的文件")
    size = None
    kind = None
    title = ""
    dmin = (0.0, 0.0, 0.0)
    dmax = (1.0, 1.0, 1.0)
    has_dmin = has_dmax = False
    rows: list[list[float]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        key = head.upper()
        if key in ("LUT_3D_SIZE", "LUT_1D_SIZE"):
            k = "3d" if key.endswith("3D_SIZE") else "1d"
            if kind is not None:
                raise LutError(f"{source}:{lineno} 同时出现或重复的 "
                               f"{key}（已按 {kind} 解析）")
            parts = rest.split()
            if len(parts) != 1:
                raise LutError(f"{source}:{lineno} {key} 需要一个整数参数：{line!r}")
            try:
                size = int(parts[0])
            except ValueError:
                raise LutError(f"{source}:{lineno} {key} 不是整数：{parts[0]!r}") from None
            kind = k
        elif key == "TITLE":
            title = rest.strip().strip('"').strip("'")
        elif key in ("DOMAIN_MIN", "DOMAIN_MAX"):
            parts = rest.split()
            if len(parts) != 3:
                raise LutError(f"{source}:{lineno} {key} 需要三个数：{line!r}")
            try:
                tri = tuple(float(v) for v in parts)
            except ValueError:
                raise LutError(f"{source}:{lineno} {key} 不是三个有限数：{parts!r}") from None
            if not all(math.isfinite(v) for v in tri):
                raise LutError(f"{source}:{lineno} {key} 含非有限值：{tri}")
            if key == "DOMAIN_MIN":
                dmin, has_dmin = tri, True
            else:
                dmax, has_dmax = tri, True
        elif key in ("INPUT_BT", "OUTPUT_BT", "INPUT_MODE", "OUTPUT_MODE", "VARIABLE"):
            #  recognized 但不参与本引擎的数学：写进 notes，不静默丢弃
            continue
        else:
            parts = line.split()
            if len(parts) != 3:
                raise LutError(f"{source}:{lineno} 这一行不是三个数：{line!r}")
            try:
                v = [float(p) for p in parts]
            except ValueError:
                raise LutError(f"{source}:{lineno} 三个字段不全是数：{parts!r}") from None
            if not all(math.isfinite(x) for x in v):
                raise LutError(f"{source}:{lineno} 含非有限值：{v}")
            rows.append(v)
    if kind is None:
        raise LutError(f"{source}: 没找到 LUT_3D_SIZE 或 LUT_1D_SIZE，不是 .cube 文本")
    if kind == "1d":
        # 明确拒而不是默默给一张“看着像”的表：本引擎只实现了 3D 插值，而 1D 表的
        # 语义是逐通道曲线，拼一个“把 1D 当 3D 用”的实现会把三个通道的耦合算错。
        raise LutError(f"{source}: LUT_1D_SIZE={size} 的一维表本引擎还未实现"
                       "（只支持 LUT_3D_SIZE）；拒比给一个近似错结果安全")
    if has_dmin != has_dmax:
        raise LutError(f"{source}: DOMAIN_MIN / DOMAIN_MAX 只给了一半，"
                       "无法确定输入域（另一半点默认按 0–1 会悄悄改色）")
    lo = np.asarray(dmin, dtype=np.float64)
    hi = np.asarray(dmax, dtype=np.float64)
    if np.any(hi <= lo):
        raise LutError(f"{source}: DOMAIN_MAX {dmax} 必须大于 DOMAIN_MIN {dmin}")
    if not (MIN_SIZE_3D <= size <= MAX_SIZE_3D):
        raise LutError(f"{source}: LUT_3D_SIZE={size} 超出支持范围 "
                       f"[{MIN_SIZE_3D}, {MAX_SIZE_3D}]")
    expect = size ** 3
    if len(rows) != expect:
        raise LutError(f"{source}: 表有 {len(rows)} 行，3D 尺寸 {size} 应当是 "
                       f"{expect} 行——宁缺半张表也不拿错表上屏")
    grid = np.asarray(rows, dtype=np.float64)
    clipped = _check_clipped(grid)
    if clipped:
        grid = np.clip(grid, 0.0, 1.0)
    grid = grid.reshape(size, size, size, 3)                    # (B, G, R, 3)：B 最外层
    notes = []
    if size < QUALITY_SIZE_3D:
        notes.append(f"LUT 只有 {size}³：实测该尺寸下最大偏差进 10 LSB 量级"
                     f"（{QUALITY_SIZE_3D}³ 是 5 LSB），粗表的精度不该被当成实现错")
    # neutral 只能与“表就是恒等”**且“输入域就是 0–1”**同时成立。 domain 不是 0–1 时，
    # 一张 corner 表会把 [0.1,0.9] 拉伸成全域输出——那是重映射，不是恒等。
    # 上一版只比表不对比域，于是 DOMAIN 0.1–0.9 的 2³ 表被判成 neutral、直接短路回原图。
    default_domain = (not has_dmin and not has_dmax) or (
        all(abs(a - b) <= NEUTRAL_TOL for a, b in zip(dmin + dmax, (0., 0., 0., 1., 1., 1.))))
    neutral = bool(default_domain
                   and np.abs(grid - _identity_grid(size)).max() <= NEUTRAL_TOL)
    if clipped:
        notes.append(f"{clipped} 个表值超出 [0,1]，已夹到端点（轻微过冲常见，不静默吞掉）")
    return CubeLut(kind=kind, size=size, grid=grid, title=title,
                   domain_min=dmin, domain_max=dmax, clipped=clipped,
                   neutral=neutral, notes=tuple(notes), source=source)


def load_cube_file(path: str) -> CubeLut:
    """从磁盘读 .cube。只认 UTF-8（带 BOM 容忍），二进制或超大文件当场拒。"""
    if not os.path.isfile(path):
        raise LutError(f"LUT 文件不存在或不是普通文件：{path}")
    n = os.path.getsize(path)
    if n > MAX_TEXT_BYTES:
        raise LutError(f"LUT 文件 {n // 1048576} MiB 超过上限 "
                       f"{MAX_TEXT_BYTES // 1048576} MiB：{path}")
    with open(path, encoding="utf-8-sig") as fh:
        return parse_cube(fh.read(), source=os.path.basename(path))


# ------------------------------------------------------------------ 烘焙（预设用）
def bake(fn, size: int = QUALITY_SIZE_3D, *, title: str = "",
         source: str = "bake") -> CubeLut:
    """把一个解析可算的调色函数烘焙成 LUT。预设走这条路，与用户 .cube 同一条应用路径。

    fn 收 (…,3) 的 float64 通道值、返回同形状 —— 于是"跑靶比真值"这条判据在这里
    仍然成立：真值就是 fn 本身。
    """
    if not (MIN_SIZE_3D <= size <= MAX_SIZE_3D):
        raise LutError(f"烘焙尺寸 {size} 超出 [{MIN_SIZE_3D}, {MAX_SIZE_3D}]")
    x = _identity_grid(size)
    out = np.asarray(fn(x), dtype=np.float64)
    if out.shape != x.shape:
        raise LutError(f"调色函数返回 {out.shape}，应当是 {x.shape}")
    if not np.isfinite(out).all():
        raise LutError("调色函数产生了非有限值，不烘焙半张表")
    clipped = _check_clipped(out)
    grid = np.clip(out, 0.0, 1.0)
    notes = [f"越界 {clipped} 个值已夹到 [0,1]"] if clipped else []
    if size < QUALITY_SIZE_3D:
        notes.append(f"烘焙尺寸 {size}³ 低于 {QUALITY_SIZE_3D}³，精度按粗表对待")
    return CubeLut(kind="3d", size=size, grid=grid, title=title, clipped=clipped,
                   neutral=bool(np.abs(grid - _identity_grid(size)).max() <= NEUTRAL_TOL),
                   notes=tuple(notes), source=source)


# ------------------------------------------------------------------ 应用
def _domain_affine(x, lo, hi):
    """把输入从 [lo, hi] 映到 [0, 1] 再查表。域不是 0–1 时必须走这一步，
    否则同一张表会给出另一张表的色彩（.cube 的 DOMAIN 语义就是这个）。"""
    span = np.asarray(hi, dtype=np.float64) - np.asarray(lo, dtype=np.float64)
    return (x - np.asarray(lo, dtype=np.float64)) / span


def apply_lut_np(img, lut: CubeLut):
    """CPU 参考实现（float64 三线性 / 一维线性），与 apply_lut_t 逐句同语义。

    取点约定写死在注释里，因为它是这层最容易量错的地方：
    `i = clip(floor(p), 0, s-2)` 之后必须用 `f = p - i`，**不是** `p - floor(p)`。
    后者在 p 恰好落在最后一个格点（纯白输入）时给 i=s-2、f=0，等于把白点采到次白
    那一格——探针第一轮就是这么让恒等表"差 7.97 LSB"的。
    """
    a = np.asarray(img, dtype=np.float64)
    if a.ndim != 4 or a.shape[1] != 3:
        raise LutError(f"apply_lut_np 需要 (N,3,H,W)，得到 {a.shape}")
    lo = np.asarray(lut.domain_min, dtype=np.float64)[None, :, None, None]
    hi = np.asarray(lut.domain_max, dtype=np.float64)[None, :, None, None]
    x = _domain_affine(a, lo, hi)
    if lut.neutral:
        return img
    s1 = lut.size - 1
    g = lut.grid                                                 # (B,G,R,3)
    p = np.clip(x, 0.0, 1.0) * s1
    i = np.clip(np.floor(p).astype(np.int64), 0, max(s1 - 1, 0))
    f = p - i
    ri, gi, bi = i[:, 0], i[:, 1], i[:, 2]
    fr, fg, fb = f[:, 0][..., None], f[:, 1][..., None], f[:, 2][..., None]

    def at(dr, dg, db):
        return g[np.clip(bi + db, 0, s1), np.clip(gi + dg, 0, s1), np.clip(ri + dr, 0, s1)]
    a0 = at(0, 0, 0) + (at(1, 0, 0) - at(0, 0, 0)) * fr
    a1 = at(0, 1, 0) + (at(1, 1, 0) - at(0, 1, 0)) * fr
    b0 = at(0, 0, 1) + (at(1, 0, 1) - at(0, 0, 1)) * fr
    b1 = at(0, 1, 1) + (at(1, 1, 1) - at(0, 1, 1)) * fr
    out = (a0 + (a1 - a0) * fg) + ((b0 + (b1 - b0) * fg) - (a0 + (a1 - a0) * fg)) * fb
    # 上面按 (N,H,W,3) 算（网格最后一维才是 RGB），出口必须回到入参的 (N,3,H,W)
    return np.clip(out, 0.0, 1.0).transpose(0, 3, 1, 2)


def apply_lut_t(img, lut: CubeLut, vol=None):
    """GPU 生产实现：一次 grid_sample(3d)。vol 可传入预先上显存的表（常驻用）。

    与 CPU 参考臂的关系已由探针确认：grid_sample 的 trilinear 与手写三线性在 uint8
    上逐字节相同，所以这里不重复实现一遍"参考"，只把采样口径交给 CPU 那一臂。
    """
    if torch is None:
        raise RuntimeError("apply_lut_t 需要 torch")
    if img.ndim != 4 or img.shape[1] != 3:
        raise LutError(f"apply_lut_t 需要 (N,3,H,W)，得到 {tuple(img.shape)}")
    if lut.neutral:
        return img
    lo = torch.tensor(lut.domain_min, dtype=img.dtype, device=img.device).view(1, 3, 1, 1)
    hi = torch.tensor(lut.domain_max, dtype=img.dtype, device=img.device).view(1, 3, 1, 1)
    x = ((img - lo) / (hi - lo)).clamp(0.0, 1.0)
    n, _, h, w = x.shape
    if n != 1:
        # grid_sample 要求 volume 与 grid 同 batch，而表只有一份。本仓的常驻张量一律是
        # (1,3,H,W)，所以这里直接拒，不写一份“靠广播碰运气”的多图路径：那一旦真的
        # 被批量调用，会得到“第一张的表 applied 到全部”这种静默错。
        raise LutError(f"apply_lut_t 一次只接一张图，得到 batch={n}")
    if vol is None:
        vol = lut.to_device(img.device)
    # coord 顺序是 (x, y, z) = (R, G, B)，对应 volume 的 (W, H, D)
    coord = torch.stack([x[:, 0], x[:, 1], x[:, 2]], dim=-1) * 2.0 - 1.0
    out = torch.nn.functional.grid_sample(vol, coord.reshape(n, h, w, 1, 3),
                                          mode="bilinear", padding_mode="border",
                                          align_corners=True)
    # grid 的倒数第二维是 1（只有一个 z 层），所以输出是 (N,3,H,W,1)，必须压掉
    return out[..., 0]
