"""线性光下的低频加减光（仿中性灰修容 / Dodge & Burn，M2-a2）。

为什么单独一个模块而不是塞进 guided.py：这一层动的是**光影**，不是纹理，判据也完全不同
（"纹理零改动"与"均值按档移动"）。而且 sRGB↔linear 这对换算是 M3 曲线/LUT 的地基，
写在这里两边都用同一份，不出现第二套 gamma 约定。

中性灰修容的数学等价是什么：Photoshop 里"中性灰图层 + 低流量加深减淡"做的是
**只在低频上加减、纹理一格不动**。直接对原图乘一个系数做不到这件事——笔触的硬边
与噪声都会被一起乘放。所以这里显式地把涂画场先带限（盒式平滑到 radius 尺度），
再在**线性光**下当曝光乘子用：

    gain = 2^(exposure · box(w, r))          # w∈[-1,1]，负=加深 正=减淡
    out  = srgb( srgb⁻¹(img) · gain )

"在线性光下"不是行话而是有后果的：sRGB 编码值上 ×2 只提亮约 0.45 档，而且会连带
把纹理一起拉开；线性光下 ×2 才恰好是一档，且乘子是**逐像素**的、与纹理无关。
"""

from __future__ import annotations

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")

from .guided import _box_np, _box_t

# 产品默认：笔触带限半径 24（代理档上约 1.5% 画面宽），曝光 0.6 档
DEFAULT_DB_RADIUS = 24
DEFAULT_DB_EXPOSURE = 0.6
# 曝光档数的硬边界：±3 档已经把 0..1 推到 1/8..8 倍，再大就是纯剪切，没有修容意义
DB_EXPOSURE_LIMIT = 3.0


def _lin_np(a: np.ndarray) -> np.ndarray:
    """sRGB 分量值 [0,1] → 线性光（IEC 61966-2-1 分段精确式，不是 2.2 次幂近似）。"""
    a = np.maximum(a, 0.0)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _slin_np(a: np.ndarray) -> np.ndarray:
    """线性光 → sRGB 分量值。与 _lin_np 互逆（浮点内），超出 [0,1] 的入参会被夹。"""
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055)


def _lin_t(a):
    a = a.clamp_min(0.0)
    return torch.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055).pow(2.4))


def _slin_t(a):
    a = a.clamp(0.0, 1.0)
    return torch.where(a <= 0.0031308, a * 12.92, 1.055 * a.pow(1.0 / 2.4) - 0.055)


def _check(exposure: float, radius: int):
    e = float(exposure)
    r = int(radius)
    # NaN 走不了比较，会一路算出 gain=NaN；inf 同理。这里不拦，后面就是整幅 NaN
    # 并且 `(1-0)*img + 0*NaN` 仍是 NaN——M1-3c 那条"非有限值不进常驻缓存"的教训。
    if not np.isfinite(e) or abs(e) > DB_EXPOSURE_LIMIT:
        raise ValueError(f"曝光档数非法：{exposure!r}（需 |exposure| ≤ {DB_EXPOSURE_LIMIT} 的有限数）")
    if r < 0:
        raise ValueError(f"修容带限半径非法：{radius!r}（需 ≥0）")
    return e, r


def _none_check(field) -> None:
    """空场请传全零数组，不要靠 None。None 当“没画过”看会把调用方的坐标错误
    当成“用户真的没画”，而上屏字节看不出任何区别——静默吞掉一个 bug。"""
    if field is None:
        raise ValueError("修容场不能为 None：空场请传全零数组")


def _shape_check(img, field, name: str) -> None:
    """场的空间尺寸必须与图一致，不接受靠广播“自动对齐”。

    这是探针拿 (1,1,1,W) 直接撞出来的：numpy 与 torch 都会把一行的场静默广播成整幅，
    于是“在眉毛上扫了一下”变成“全图提亮半档”——语义完全错，一个异常也不抛。
    与 M1-3b 那条「掩膜尺寸必须对得上代理帧尺寸」是同一条防线，只是这里更阴：
    尺寸差 1 才会报错，差一整维反而合法。
    """
    if field.ndim < 2 or tuple(field.shape[-2:]) != tuple(img.shape[-2:]):
        raise ValueError(f"{name} 空间尺寸 {tuple(getattr(field, 'shape', ()))[-2:]} != "
                         f"图 {tuple(img.shape[-2:])}：修容场必须与图同尺寸，"
                         "靠广播对齐会把一行笔触静默拉伸成整幅")


def _zero_gain_hold(img, ws, out):
    """场恰好为零的像素逐字节还原值，不让 sRGB↔linear 的浮点往返碰它。

    为什么需要：gain 在 ws=0 处确实是精确的 1.0，`slin(lin(v)·1)` 看上去就是恒等——
    但对**非格点**的 v 不是。生产通路里两个操作数（`img` 与磨皮成品 `retouched`）都是
    管线中间值，不在 256 个格点上；往返会把它挪开最后一位 float32，一旦落在 ×255 的
    .5 边界上就翻 1 LSB。m2-dnb-bench 的 1e 量到：三支笔之外“场恰好为零”的区域仍有
    0.0045% 像素被重量化。消除笔那条“笔外逐字节不动”的标准，修容也必须成立。

    走过的弯路，记下来免得再走：上一轮我先拿“几何圆外”当判据（错：那里有带限场的
    合法拖尾，真图代理档上三支笔之外仍有 0.30% 像素 ws≠0，|ws| 最大 0.0087 → 增益
    1.0036），发现守卫不消那部分就把它撤了——也错。判据要卡在 **ws 恰好为零**，
    而它确实需要这个守卫，只是需要的原因比“往返不恒等”这一句细一层。
    """
    if isinstance(out, np.ndarray):
        return np.where(ws == 0.0, img, out)
    return torch.where(ws == 0.0, img, out)


def dodge_burn_np(img: np.ndarray, field: np.ndarray, exposure: float = DEFAULT_DB_EXPOSURE,
                  radius: int = DEFAULT_DB_RADIUS) -> np.ndarray:
    """在 img 上按涂画场做低频加减光（CPU 参考实现）。

    field 形状与 img 广播兼容（(1,1,H,W) 或 (1,C,H,W)），值域 [-1,1]：负=加深、正=减淡。
    必须与 dodge_burn_t 逐句同语义。

    **空场必须短路**：不短路的话 `srgb(linear(img))` 的往返会在灰阶平坦区抖 ±1 LSB，
    于是"没画修容 ⇒ 上屏逐字节等于解码原图"这条承诺会被一个纯数值伪证打破。
    短路同时是免费路径（没画过修容的图一个算子都不多跑）。

    非空场时“场没盖到的地方逐字节不动”由 `_zero_gain_hold` 保证：那里的 gain 虽然
    恰好是 1.0，但 `slin(lin(v))` 只对 256 个格点恒等，而生产操作数不在格点上。
    """
    e, r = _check(exposure, radius)
    _none_check(field)
    f = np.asarray(field)
    src = np.asarray(img)
    _shape_check(src, f, "修容场")
    if e == 0.0 or f.size == 0 or not f.any():
        return img
    ws = _box_np(f.astype(np.float64) if f.dtype != np.float64 else f, r)
    gain = np.power(2.0, e * ws)
    out = _slin_np(_lin_np(src.astype(np.float64)) * gain).astype(src.dtype)
    return _zero_gain_hold(src, ws, out)


def dodge_burn_t(img, field, exposure: float = DEFAULT_DB_EXPOSURE,
                 radius: int = DEFAULT_DB_RADIUS):
    """GPU 生产实现，与 dodge_burn_np 逐句同语义（含空场短路与零增益区逐字节还原）。"""
    e, r = _check(exposure, radius)
    _none_check(field)
    _shape_check(img, field, "修容场")
    if e == 0.0 or not bool(field.any()):
        return img
    ws = _box_t(field.to(torch.float64) if field.dtype != torch.float64 else field, r)
    gain = torch.pow(torch.tensor(2.0, dtype=torch.float64, device=img.device),
                     e * ws.to(torch.float64)).to(img.dtype)
    return _zero_gain_hold(img, ws, _slin_t(_lin_t(img) * gain))
