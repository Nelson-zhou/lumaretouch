"""裁剪 / 旋转（P0：`lnx.crop.v1`）。

冻结注册表里这一条的中性就是 `rect=[0,0,1,1]`、`rotation=0`，语义是"不剪不转"，
而 ADR-0003 把"中性 = 逐字节恒等"定成了硬门禁：所以这一层的第一件事不是算变换，
而是**认出恒等并原样交出那个对象**（`is` 同一份，不是"算出来恰好一样"）。

两条臂（`*_np` 解析真值 / `*_t` GPU 生产）必须同算式——与曝光/白平衡那层同一条纪律。
这里的"同算式"具体指：同一个逆仿射、同一个双线性权重、同一个画布尺寸的算法
（旋转后的外接框），而不是"np 用 PIL、t 用 torch 各自的默认 resize"——那样两臂
会在边界像素上长期不一致，而对拍就成了调容差。

90° 整数倍走**转置**而不是插值：那是一条无损路径，用户按"右转 90°"不该看到
任何重采样伪影，也不该在导出里付出插值的代价。
"""
from __future__ import annotations

import math

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")

EPS = 1e-12
MAX_ANGLE = 180.0             # 注册表：[-180, 180]，±180 是单值覆盖全圆的唯一自然区间


class GeometryError(ValueError):
    """参数不在本层可算域内。宁可拒，也不夹：默默夹一次旋转角就是替用户改了构图。"""


def check(rect, rotation_degrees: float) -> tuple[float, float, float, float]:
    """校验并归一成 (x0, y0, x1, y1)。量程逐条按冻结注册表来。

    `rect_normalized` 的原件写的是逐坐标 [0,1] 与 `x0<x1;y0<y1`——这里把它写成
    **可执行的**判据（严格小于），因为零宽/零高的裁剪框不是一个"退化的裁剪"，
    而是一张 0 像素的图：那会让下游每一层都拿到空数组，报错点跑到几百行之外。
    """
    a = np.asarray(rect, dtype=np.float64).ravel()
    if a.size != 4:
        raise GeometryError(f"rect_normalized 需要 4 个数，收到 {a.size} 个")
    if not np.isfinite(a).all():
        raise GeometryError("rect_normalized 含 NaN/Inf")
    x0, y0, x1, y1 = (float(v) for v in a)
    for name, v in (("x0", x0), ("y0", y0), ("x1", x1), ("y1", y1)):
        if not (0.0 <= v <= 1.0):
            raise GeometryError(f"{name}={v} 越界（逐坐标需要落在 [0,1]）")
    if not (x0 < x1 and y0 < y1):
        raise GeometryError(f"裁剪框必须 x0<x1 且 y0<y1，收到 [{x0}, {y0}, {x1}, {y1}]")
    r = float(rotation_degrees)
    if not math.isfinite(r):
        raise GeometryError("rotation_degrees 是 NaN/Inf")
    if abs(r) > MAX_ANGLE + EPS:
        raise GeometryError(f"rotation_degrees={r} 越界（需要 [-{MAX_ANGLE:.0f}, {MAX_ANGLE:.0f}]）")
    return x0, y0, x1, y1, r


def is_identity(rect, rotation_degrees: float) -> bool:
    """恒等判据与 `check` 同源，不另写一份"看起来差不多"的比较。"""
    try:
        x0, y0, x1, y1, r = check(rect, rotation_degrees)
    except GeometryError:
        return False
    return (x0 <= EPS and y0 <= EPS and (1.0 - x1) <= EPS and (1.0 - y1) <= EPS
            and abs(r) <= EPS)


def _cut(n: int, a: float, b: float) -> tuple[int, int]:
    """把归一化边界换成整数像素窗口。唯一的尺寸出处：`out_size` 与两条臂的切片
    都必须调它。上一版 `out_size` 算的是 round(n*(b-a))，切片算的是
    round(n*b)-round(n*a)，两者在 0.1/0.9 这种边上差 1 像素——于是"预览与导出共用
    一个尺寸算法"这句注释是假的，测试把它照出来了。"""
    lo = min(max(int(round(n * a)), 0), n - 1)
    hi = min(max(int(round(n * b)), lo + 1), n)
    return lo, hi


def out_size(w: int, h: int, rect, rotation_degrees: float) -> tuple[int, int]:
    """裁剪框 + 旋转后的**真实**输出尺寸（(宽, 高)）。

    导出层要用它算落盘尺寸，预览层要用它把结果缩放回代理画布——两边必须同一个函数，
    否则"预览里看到的构图"与"文件里的像素"会在最后一行像素上分叉。
    """
    x0, y0, x1, y1, r = check(rect, rotation_degrees)
    xa, xb = _cut(w, x0, x1)
    ya, yb = _cut(h, y0, y1)
    cw, ch = xb - xa, yb - ya
    if abs(r % 90.0) < 0.5 - EPS:        # 整数倍 90°：转置，画布是精确的宽高互换
        k = int(round(r / 90.0)) % 4
        return (cw, ch) if k % 2 == 0 else (ch, cw)
    # 任意角：外接框按旋转后的包围盒算（与 crop_rotate_* 里用的同一个式子）
    a = math.radians(r)
    ca, sa = abs(math.cos(a)), abs(math.sin(a))
    return (max(1, int(round(cw * ca + ch * sa))), max(1, int(round(cw * sa + ch * ca))))


def _quarter_turn(arr: np.ndarray, k: int) -> np.ndarray:
    """k 次逆时针 90°（无损）。PIL/numpy 的 rot90 对 (H,W,C) 用 axes=(0,1) 即可。"""
    return np.rot90(arr, k=k % 4, axes=(0, 1))


# ------------------------------------------------------------------ numpy 真值臂
def crop_np(arr: np.ndarray, rect) -> np.ndarray:
    """按归一化框取整数像素窗口。整数边界用 round 而不是 floor：
    floor 会让"拖到正中"这种 0.5 的分界线系统性偏左上一像素。"""
    x0, y0, x1, y1, r = check(rect, 0.0)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    a, b = _cut(w, x0, x1)
    c, d = _cut(h, y0, y1)
    return np.ascontiguousarray(arr[c:d, a:b])


def rotate_np(arr: np.ndarray, degrees: float) -> np.ndarray:
    """任意角旋转：逆仿射 + 双线性，输出画布是旋转后的外接框。90° 整数倍走转置。"""
    _, _, _, _, r = check([0.0, 0.0, 1.0, 1.0], degrees)
    if abs(r) < EPS:
        return arr
    if abs(abs(r) % 90.0) < 0.5 or abs(abs(r) % 90.0 - 90.0) < 0.5:
        return np.ascontiguousarray(_quarter_turn(arr, int(round(-r / 90.0))))
    h, w = int(arr.shape[0]), int(arr.shape[1])
    src = np.asarray(arr, dtype=np.float64)
    a = math.radians(r)
    # 屏幕坐标（y 向下）里"正角=顺时针"是这个行业的直觉（Lightroom 右转为正），
    # 逆映射用 R(-a) 把目标像素坐标映回源坐标
    ca, sa = math.cos(-a), math.sin(-a)
    ow, oh = out_size(w, h, [0.0, 0.0, 1.0, 1.0], r)
    ys, xs = np.mgrid[0:oh, 0:ow].astype(np.float64)
    # 绕各自中心旋转：目标中心 (ow-1)/2 ↔ 源中心 (w-1)/2
    dx = xs - (ow - 1) / 2.0
    dy = ys - (oh - 1) / 2.0
    sx = ca * dx - sa * dy + (w - 1) / 2.0
    sy = sa * dx + ca * dy + (h - 1) / 2.0
    out = _sample_bilinear_np(src, sx, sy)
    return np.ascontiguousarray(out)


def _sample_bilinear_np(src: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """双线性取样；画布外的部分取 0（旋转带进来的角）。src 是 float64 (H,W,C)。"""
    h, w, c = src.shape
    x0 = np.floor(sx).astype(np.int64); y0 = np.floor(sy).astype(np.int64)
    fx = sx - x0; fy = sy - y0
    valid = (x0 >= 0) & (x0 < w - 1) & (y0 >= 0) & (y0 < h - 1)
    x0c = np.clip(x0, 0, w - 2); y0c = np.clip(y0, 0, h - 2)
    p00 = src[y0c, x0c]; p10 = src[y0c, x0c + 1]
    p01 = src[y0c + 1, x0c]; p11 = src[y0c + 1, x0c + 1]
    fx3 = fx[..., None]; fy3 = fy[..., None]
    top = p00 + (p10 - p00) * fx3
    bot = p01 + (p11 - p01) * fx3
    v = top + (bot - top) * fy3
    v = np.where(valid[..., None], v, 0.0)
    return v


def crop_rotate_np(arr: np.ndarray, rect, rotation_degrees: float, *, uint8: bool = True) -> np.ndarray:
    """先剪后转。恒等时**原样交出入参**（`is` 同一份），逐字节恒等由这条短路给出。"""
    if is_identity(rect, rotation_degrees):
        return arr
    x0, y0, x1, y1, r = check(rect, rotation_degrees)
    out = crop_np(arr, (x0, y0, x1, y1))
    if r != 0.0:
        if uint8 and out.dtype == np.uint8:
            out = rotate_np(out.astype(np.float64), r)
            return np.rint(np.clip(out, 0.0, 255.0)).astype(np.uint8)
        out = rotate_np(out, r)
    return out


# ------------------------------------------------------------------ torch 生产臂
def _sample_bilinear_t(src, sx, sy):
    """与 numpy 臂逐式同的双线性：同一个 floor、同一组权重、画布外取 0。

    不用 F.grid_sample：它的默认坐标系（-1..1 且像素中心在 (i+0.5)/n*2-1）与这里
    的"像素索引坐标"差半个 texel，两臂会长期错开那半格——对拍最后就变成调容差。
    """
    h, w, c = src.shape
    x0 = torch.floor(sx).to(torch.long); y0 = torch.floor(sy).to(torch.long)
    fx = (sx - x0.to(src.dtype))[..., None]; fy = (sy - y0.to(src.dtype))[..., None]
    valid = (x0 >= 0) & (x0 < w - 1) & (y0 >= 0) & (y0 < h - 1)
    x0c = x0.clamp(0, w - 2); y0c = y0.clamp(0, h - 2)
    p00 = src[y0c, x0c]; p10 = src[y0c, x0c + 1]
    p01 = src[y0c + 1, x0c]; p11 = src[y0c + 1, x0c + 1]
    top = p00 + (p10 - p00) * fx
    bot = p01 + (p11 - p01) * fx
    v = top + (bot - top) * fy
    return torch.where(valid[..., None], v, torch.zeros_like(v))


def crop_rotate_t(arr, rect, rotation_degrees: float, *, uint8: bool = True):
    """生产臂。入参可以是 (H,W,3) 的 tensor 或 ndarray；恒等时原样交出（零成本）。"""
    if torch is None:
        raise GeometryError("裁剪/旋转的生产臂需要 torch")
    if is_identity(rect, rotation_degrees):
        return arr
    x0, y0, x1, y1, r = check(rect, rotation_degrees)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    a, b = _cut(w, x0, x1)
    c, d = _cut(h, y0, y1)
    cur = arr[c:d, a:b]
    if r == 0.0:
        return cur
    ch, cw = int(cur.shape[0]), int(cur.shape[1])
    if abs(abs(r) % 90.0) < 0.5 or abs(abs(r) % 90.0 - 90.0) < 0.5:
        return torch.rot90(cur, k=int(round(-r / 90.0)) % 4, dims=(0, 1)).contiguous()
    ow, oh = out_size(cw, ch, [0.0, 0.0, 1.0, 1.0], r)
    dtype = cur.dtype if cur.is_floating_point() else torch.float32
    src = cur.to(dtype)
    ys, xs = torch.meshgrid(torch.arange(oh, dtype=dtype, device=cur.device),
                            torch.arange(ow, dtype=dtype, device=cur.device), indexing="ij")
    ang = math.radians(-r)
    ca, sa = math.cos(ang), math.sin(ang)
    dx = xs - (ow - 1) / 2.0
    dy = ys - (oh - 1) / 2.0
    sx = ca * dx - sa * dy + (cw - 1) / 2.0
    sy = sa * dx + ca * dy + (ch - 1) / 2.0
    out = _sample_bilinear_t(src, sx, sy)
    if uint8 and not cur.is_floating_point():
        out = out.round().clamp_(0.0, 255.0).to(torch.uint8)
    return out


def geometry_state(ev_free_rect, rotation_degrees: float) -> dict:
    """给状态面回用的读数：算得出尺寸，也让 UI 能显示"当前输出多大"。"""
    x0, y0, x1, y1, r = check(ev_free_rect, rotation_degrees)
    return {"rect": [x0, y0, x1, y1], "rotation_degrees": r,
            "limits": {"rect": [0.0, 1.0], "rotation": [-MAX_ANGLE, MAX_ANGLE]},
            "neutral": is_identity((x0, y0, x1, y1), r)}
