"""内置预设（M3-b）：韩系奶油 / 质感冷白 = 一张烘焙色彩观 + 三个肤色定向参数。

拆成两半不是实现方便，是**精度口径决定的**（`gpuspike/m3d.py` 定架构，`m3e.py` 直接量
生产算子）：

· 色彩观（矩阵 + 抬黑 + 高光滚降 + 饱和缩放）在 RGB 空间里是平滑函数。m3e 的 A 节在
  真图（928×616）与全色域 30 万个随机点 + 8 个角点上量：33³ 表复现它**最大 2 LSB**
  （连续误差 1.45–1.99 LSB），17³ 是 4 LSB，64³ 是 1 LSB——所以每个预设自带的
  `look_lsb=2` 是量出来的，不是许愿——它走 `ops/lut.py` 那条已经验过的表通路，
  与用户 .cube 同一条应用路径、同一套保证。
· 肤色定向（HSL 窗口）在 RGB 里有一条陡峭边界，**同一组参数**烘进 33³ 表要差到
  6.8–9.3 LSB（连续）/ 9–10% 像素与真值不同；而逐帧内核与 f64 参考只差 1 LSB
  （而且只在贴量化边界的那 1.7e-6 像素上）——所以它绝不烘进表，走 `ops/grade.py`。

clean-room 说明：这两个预设是本仓自己写的解析函数烘出来的，不引任何第三方 .cube
素材，也不参照任何厂商的调色数据；数值口径全部来自真机实测。

判据去哪了：`packaging/m3-color-bench.py` 的第 4 节按这里声明的 `look_lsb` 卡表复现，
按方向与幅度卡肤色窗口（窗内往哪动、窗外逐字节不动），`engine/tests/test_presets.py`
卡结构与拒绝路径。数字一改必须同步改判据——所以每个数都写了出处。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .lut import QUALITY_SIZE_3D, CubeLut, bake


def _matrix(x, m):
    """行和为 1 的跨通道矩阵：中性灰保持不动。

    这不是审美选择而是度量选择——行和不为 1 时矩阵本身就在改明度，后面那个
    "亮度只由 tone 段负责"的口径就散了；行和为 1 时，冷暖只动色度不动浓度。
    """
    return np.clip(np.asarray(x, dtype=np.float64) @ np.asarray(m, dtype=np.float64).T, 0.0, 1.0)


def _rolloff(x, keep: float, knee: float):
    """高光滚降：越亮的区域按比例压下去（平滑，无拐点以外的不连续）。"""
    hi = x.mean(axis=-1, keepdims=True)
    return x * (1.0 - keep * np.clip(hi - knee, 0.0, None))


def _sat(x, scale: float, lum_w):
    """饱和缩放：向"亮度色"插值。`lum_w` 是明度权重（行和仍为 1）。"""
    lum = x @ np.asarray(lum_w, dtype=np.float64)
    lum = np.repeat(lum[..., None], 3, axis=-1)
    return np.clip(lum + (x - lum) * scale, 0.0, 1.0)


# ---- 韩系奶油：抬黑、暖化、压高光、降饱和，整体柔但不糊
CREAMY_MATRIX = [[1.045, -0.030, -0.015],
                 [-0.020, 1.030, -0.010],
                 [-0.030, -0.010, 1.040]]
CREAMY_TOE = 0.035                     # 抬黑 3.5%：胶片式灰底
CREAMY_ROLL = 0.12                     # 高光压 12%（knee 以上）
CREAMY_SAT = 0.90                      # 全局降饱和 10%（奶油感）
CREAMY_LUM = [0.2126, 0.7152, 0.0722]  # Rec.709 权重，行和为 1
# 33³ 表复现这张色彩观的实测上限（gpuspike/m3e.py A 节与 m3-color-bench 第 4 节：
# 真图 928×616 + 全色域 30 万随机点/8 角点，量化最大 2 LSB、连续最大 1.90 LSB）
CREAMY_LOOK_LSB = 2


def creamy_look(x):
    y = _matrix(x, CREAMY_MATRIX)
    y = np.clip(CREAMY_TOE + y * (1.0 - CREAMY_TOE), 0.0, 1.0)
    y = _rolloff(y, CREAMY_ROLL, 0.72)
    return _sat(y, CREAMY_SAT, CREAMY_LUM)


# ---- 质感冷白：不抬黑、保结构与对比，阴影加一点青、高光收中性
COOL_MATRIX = [[1.020, -0.010, -0.010],
               [-0.020, 1.015, 0.005],
               [0.000, -0.010, 1.010]]
COOL_LIFT = (0.0, 0.004, 0.012)        # 只抬蓝/绿通道底：冷而不脏
COOL_ROLL = 0.06
COOL_SAT = 0.965
COOL_LUM = [0.2126, 0.7152, 0.0722]
# 同上口径（m3e A 节与跑靶第 4 节：真图与全域量化最大都是 2 LSB、连续最大 1.99 LSB）
COOL_LOOK_LSB = 2


def coolwhite_look(x):
    y = _matrix(x, COOL_MATRIX)
    y = np.clip(y + np.asarray(COOL_LIFT, dtype=np.float64) * (1.0 - y), 0.0, 1.0)
    y = _rolloff(y, COOL_ROLL, 0.80)
    return _sat(y, COOL_SAT, COOL_LUM)


@dataclass(frozen=True)
class Preset:
    """一个预设 = 一张色彩观表 + 三个肤色定向增量。两半各自可独立关闭。"""

    name: str
    title: str
    look: object                    # (…,3) float64 → (…,3)：解析真值
    dh: float                       # 肤色色相移动（占整圈比例）
    ds: float                       # 肤色饱和相对量（−0.18 = 降 18%）
    dv: float                       # 肤色明度相对量
    look_lsb: int                   # 33³ 表复现色彩观的实测上限（判据，不是许愿）
    size: int = QUALITY_SIZE_3D


PRESETS = {
    # 奶油：往黄一侧偏一点（压红），降饱和、提亮皮肤——影楼"奶"字就是这个
    "creamy": Preset("creamy", "韩系奶油", creamy_look,
                     dh=0.006, ds=-0.14, dv=0.05, look_lsb=CREAMY_LOOK_LSB),
    # 冷白：皮肤降饱和更多、提亮更多，观感保结构与对比
    "coolwhite": Preset("coolwhite", "质感冷白", coolwhite_look,
                        dh=-0.004, ds=-0.18, dv=0.07, look_lsb=COOL_LOOK_LSB),
}


class PresetError(ValueError):
    """预设名不存在，或预设的定义本身跑不通。

    它不是 KeyError：协议层要把“你写了个错名字”当参数拒接而不是当内部控制流捕，
    而 `except Exception` 护着的一串里混着一个语义不同的键错，下次改版就没人记得它为什么在那。
    """


def names() -> list:
    return sorted(PRESETS)


def get_preset(name: str) -> Preset:
    p = PRESETS.get(str(name))
    if p is None:
        raise PresetError(f"没有这个预设：{name!r}（可用：{', '.join(names())}）")
    return p


# 旧名保留一个别名：本仓已有几个探针（gpuspike/m3e.py）按 `presets.get` 写的
get = get_preset


def preset_lut(name: str) -> CubeLut:
    """把预设的色彩观烘成 33³ 表，source 写成 `preset:<名>`：事件里必须能说出话。"""
    p = get_preset(name)
    cube = bake(p.look, p.size, title=p.title, source=f"preset:{p.name}")
    if cube.clipped:
        # 色彩观的每一步都夹在 [0,1] 里，烘出来还越界就说明定义写错了，不是"轻微过冲"
        raise ValueError(f"预设 {name} 的色彩观有 {cube.clipped} 个越界表值，"
                         "说明某一步没夹域——不拿半截预设上屏")
    return cube


def preset_grade(name: str) -> tuple:
    p = get_preset(name)
    return (p.dh, p.ds, p.dv)
