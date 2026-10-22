"""眼牙局部增强（LNX-PORTRAIT-009）：眼白、虹膜、牙齿三个**独立启停**的子功能。

冻结件（《开发验收用例.json》PORTRAIT-009）的 then 只有三句：无虹膜意外改色、
无牙齿过曝或越界、每子功能独立启停。这三句说的都不是"效果好不好看"，而是"不许出
事故"。所以本层的每一格都按**可证的构造性质**实现，而不是按观感调参：

1. **色相一条通道都不碰。** 三个子效全部写成 HSV 里 s 的乘性量与 v 的“乘性推高但
   夹住天花板”形式，h 从头到尾是同一个数（`_sub_effects` 的签名里没有 h）。于是
   “无虹膜意外改色”是结构事实而不是观感：一手实测三张变体上窗口内 |Δh| 最大
   1.4e-15（float64 结合律量级），虹膜盘内 ≤ 2.3e-16。
   （注：拿“量化后重算的 HSV 色相”当普适判据本身就不成立：无彩度像素的色相本来就
   无定义，1 LSB 的舍入就能把 s≈0.05 的像素从一个扇区推到另一个。所以判据只对有
   彩度的区域提，数字见 test_enhance。）乘性还顺带挡住眼镜框与高光：s=0 的中性像素
   `0*(1+k)` 恒为 0，永远不会被“上色”。
2. **过曝护栏是形式本身。** 提亮一律写成 `v' = min(v·(1 + k·a·w), max(v, V_CEIL))`：
   乘性而不是加法，是为了**保住牙齿/眼白自己的层次**（牙缝与龈缘的暗部按比例一起走，
   不会被抹成一块白板）；上界 `max(v, V_CEIL)` 则让“已经比天花板亮的像素”一项也不动，
   而比它暗的像素最多只能推到 V_CEIL。于是“把已经在剪切带里的像素推到 255”这件事在
   代数上不可能发生（实测三张样本上 at255 前后相等，见验收报告），而不是事后挑一张图
   看看有没有过曝。牙齿/眼白的去黄同理是乘性下降，只会更淡，永远不会反转成"更黄"。
3. **越界由两道构造保证。** 掩膜只在眼睑环 / 虹膜圆盘 / 唇外环这几个几何多边形内部
   取值（星形栅格化按逐射线与边段**精确求交**，多边形外恒 0，只有 feather 那一圈软边
   例外——它的宽度由窗口一并包住，见 `geometry()` 里那段"先算 feather 后定窗口"），
   每个子功能再叠一道相对内容门（比本池均值更亮/更淡），
   于是睫毛、眼线、唇面、牙缝阴影被门掉，而不是被羽化糊过去。栅格化前先做星形校验，
   不满足就**整块拒**并在事件里写原因——侧脸到唇弓不再星形时，宁可没有这一层。

不是神经网络（DoD 严禁伪装 AI）
--------------------------------
掩膜 = MediaPipe FaceMesh 478 点几何（Apache 2.0，权重内嵌）+ 相对亮度/饱和的统计判据。
它是规则，不是分割网络，也不叫 AI。模块名、事件字段与 UI 文案一律写"几何掩膜 + 内容门"，
不出现"智能识别/AI 修复"这种说法。

链上位置以 vram.retouch 的真实调用为准：原有眼牙 `apply_enhance` 仍在
`apply_deform` 之后、`apply_exposure` 之前。本次不把这条旧链描述成形变前处理。
新增的八区域面部祛纹只在这里复用参数协议，不进入 `_sub_effects`：其冻结修复源
推导出的独立修正由专门消费者在自动形变之前叠加，随后与像素一起采样移动。
曝光、白平衡与后续风格调色仍处理已经叠加的像素，不回写祛纹分析源。
与 `apply_grade` 的口径差别要写清：定向层的窗口看的是**屏幕上那份颜色**（"所见即所调"），
而本层的内容门看的是**源片那份颜色**——它判的是"这里是不是牙/是不是眼白"（身份），
身份必须在未上色的像素上判，否则一张橙色 LUT 会把嘴唇认成牙齿。

一次性分析 vs 每帧
------------------
权重（几何 ∩ 内容门）在**挂层时**算一次（`geometry()` + `refine()`），每帧只跑
`enhance_t` 的逐点乘加。这不是优化洁癖：内容门要算池均值，每帧一次就是每帧一次 D2H
同步，而拖滑块时那正是断帧的来源。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..optional_dependencies import optional_module
from .. import facial_wrinkle_state as WRINKLES

torch = optional_module("torch")

from .deform import (IRIS_LEFT, IRIS_RIM_LEFT, IRIS_RIM_RIGHT, IRIS_RIGHT, LIP_INNER_BOTTOM,
                     LIP_INNER_TOP, MOUTH_CORNER_LEFT, MOUTH_CORNER_RIGHT)
from .grade import hsv_to_rgb_np, rgb_to_hsv_np, smoothstep

AMOUNT_KEYS = ("sclera", "iris", "teeth", "dark_circles", "eye_bags", "veins", "catchlight_left", "catchlight_right") + WRINKLES.INTENT_KEYS
EFFECT_KEYS = tuple(key for key in AMOUNT_KEYS if key != WRINKLES.LINK_KEY)
SUBS = ("sclera", "iris", "teeth")      # 三个子功能，顺序即权重场第 0 轴的顺序
AMOUNT_LIMIT = 1.0                      # 滑块值域 [0,1]；这一层没有负档（"反向"无安全含义）
NUM_LANDMARKS = 478

# ---- 人脸拓扑：本模块用到的环 -------------------------------------------------
# 单点下标（虹膜中心/嘴角/内唇上下中点）从 ops/deform.py import，不在这里抄第二份：
# 两个模块对同一批下标必须只有一个解释。
# 16 点眼睑环（左右互为镜像）。**这不是照抄记忆**：test_enhance 在真 MediaPipe 的夹具上
# 量三件事——环必须把虹膜中心包在里面、上下眼睑必须分居中心线两侧、环对中心的角覆盖
# 必须恰好绕一圈（`_star_ok`）。错了那条就红。
EYE_RING_LEFT = (33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7)
EYE_RING_RIGHT = (263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249)
# 唇外环的两条链：都从 61 走到 291，一条过 0（上缘），一条过 17（下缘）。串起来就是围绕
# 整张唇（含开口）的一圈。上/下的归属同样由 test_enhance 在真夹具上按几何判
# （0 必须在嘴角连线之上、17 必须在之下），不靠注释自证。
LIP_CHAIN_UPPER = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291)
LIP_CHAIN_LOWER = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291)

# ---- 三个子效的量 --------------------------------------------------------------
# 数值由 .scratch/enh_probe3.py 在三张变体夹具上量出来定（读数已归档进验收记录）。
# V_CEIL 取 0.965 而不是 0.94：自然牙与巩膜本来就落在 0.90–0.96 那一档，天花板低于它
# 就等于“这一层最多动 4 LSB”——护栏把效果拦没了不等于效果好。0.965 仍在 255 之下，
# 实测 at255 的像素数前后相等（不增），所以“不许过曝”与“看得见效果”能同时成立。
V_CEIL = 0.965           # 提亮天花板：v ≥ 它的像素一点不动，比它低的最多被推到它
SCLERA_LIFT = 0.22       # 眼白满档的乘性提亮系数（×1.22，再被天花板夹住）
SCLERA_DESAT = 0.30      # 眼白满档去黄幅度（s 乘性下降，最多降到 1−0.30 倍）
IRIS_SAT = 0.55          # 虹膜满档饱和增益（×1.55；乘性 → 中性像素恒为 0 变化）
IRIS_S_CEIL = 0.92       # 虹膜饱和上限：本来就比它艳的不再往上推（不顶出 1.0 的断层）
IRIS_LIFT = 0.14         # 虹膜满档乘性提亮（比牙齿小得多：虹膜发白就是"假眼睛"）
TEETH_LIFT = 0.35
TEETH_DESAT = 0.35       # 牙齿满档去黄
# 内容门的相对系数。判据一律拿"本池自己的均值"当基准，不写绝对阈值——理由是深肤色
# 与低光：绝对阈值（比如 s<0.30）在暗皮上会把牙齿整片判没，在亮皮上又会把唇面误收进来。
# 相对量在两种皮上都只是"比这片区域的平均更淡/更亮"这一句话。
SCLERA_S_OF_IRIS = 0.62      # 眼白要比虹膜盘的饱和均值淡到这个比例以下
SCLERA_S_SPAN = 0.60         # 门的软边宽度（相对上界）
SCLERA_V_OF_POOL = 0.86      # 眼白亮度下界（相对本池均值）：睫毛/眼线/镜框横梁在这里被掉出去
SCLERA_V_SPAN = 1.00
IRIS_S_OF_POOL = 0.24        # 虹膜门：比盘面均值淡太多的（高光、镜片反光）不收
IRIS_S_SPAN = 0.48
TEETH_S_OF_POOL = 0.72       # 牙齿要比口腔内容均值淡
TEETH_S_SPAN = 0.78
TEETH_V_OF_POOL = 1.06       # 且要比口腔内容均值亮
TEETH_V_SPAN = 0.96
# 开口度判据：内唇上下两点（13/14）的竖直间距 / 嘴宽。闭上时这两点几乎重合。
MOUTH_OPEN_MIN = 0.055
# 检测抖动会让闭嘴样本的 13/14 也分开一点，所以还要求"带里真找到了牙齿"
# （门后像素数 ≥ TEETH_MIN_PX）才点亮这一子层，否则报 reason 而不是硬画。
TEETH_MIN_PX = 12
EYE_IRIS_R_MIN = 1.0     # 虹膜半径低于 1 px 画不出可信的盘（远脸/小脸）
STAR_RAYS = 120          # 星形校验的射线数
REGION_PAD_PX = 6.0      # 窗口外扩的**下限**（真正的余量由下面两个 feather 推出来）
# 软边宽度系数：掩膜不是剪影，硬边界会在眼睑/唇缘留一条可见的接缝（"无拼缝"那句 then
# 判的就是它）。系数按部位尺寸给，不按画幅给——同一张图缩到 1/4，接缝也该等比变细。
EYE_FEATHER_OF_IRIS = 0.14   # 眼裂软边 = 0.14 × 虹膜半径
LIP_FEATHER_OF_MOUTH_W = 0.05  # 唇外环软边 = 0.05 × 嘴宽（比眼的绝对值大，窗口因此更宽）


class EnhanceError(ValueError):
    """参数非法、几何不可用、或产出非有限值。整条拒绝，不留半截状态。"""


def check_amounts(amounts) -> dict:
    """三个数的唯一校验口径（协议层、常驻层、导出层共用）。

    与 deform.check_amounts 同一条铁律：NaN 比大小恒为 False，不先拦就会被当"合法"
    写进常驻层，然后每帧渲染才抛——现场与病因隔两个模块。
    """
    if isinstance(amounts, dict):
        given = amounts
    else:
        raise EnhanceError(f"enhance 参数要是字典，得到 {type(amounts).__name__}")
    unknown = sorted(set(given) - set(AMOUNT_KEYS))
    if unknown:
        raise EnhanceError(f"enhance 不认这些子功能：{', '.join(unknown)}"
                           f"（可用：{', '.join(AMOUNT_KEYS)}）")
    # Validate family metadata before legacy float conversion: bool/string and
    # fractional unlock values must never become accepted continuous amounts.
    try:
        wrinkle_values = WRINKLES.check(given)
    except ValueError as error:
        raise EnhanceError(str(error)) from None
    out = {}
    for k in AMOUNT_KEYS:
        if k in wrinkle_values:
            out[k] = wrinkle_values[k]
            continue
        v = given.get(k, 0.0)
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise EnhanceError(f"{k}={v!r} 不是有限数（需要 [0,{AMOUNT_LIMIT}] 内的数）") from None
        if not math.isfinite(f) or not 0.0 <= f <= AMOUNT_LIMIT:
            raise EnhanceError(f"{k}={f} 超出范围 [0, {AMOUNT_LIMIT}]")
        out[k] = f
    return out


def is_identity(amounts) -> bool:
    """校验过才算数：非法值不是"没活"，是"要拒"。"""
    a = check_amounts(amounts)
    return all(a[k] == 0.0 for k in SUBS)


def _landmark_pixels(landmarks, h: int, w: int) -> np.ndarray:
    """(478,3) 归一化 → (478,2) 画布像素。数量、有限性与坐标域在这里一次校掉。"""
    lm = np.asarray(landmarks, dtype=np.float64)
    if lm.ndim != 2 or lm.shape[0] != NUM_LANDMARKS or lm.shape[1] < 2:
        raise EnhanceError(f"关键点必须是 ({NUM_LANDMARKS},2|3)，得到 {lm.shape}")
    if not np.isfinite(lm[:, :2]).all():
        raise EnhanceError("关键点含非有限值，整层拒绝")
    if lm[:, 0].min() < -1e-6 or lm[:, 0].max() > 1.0 + 1e-6 \
            or lm[:, 1].min() < -1e-6 or lm[:, 1].max() > 1.0 + 1e-6:
        # 归一化坐标越界通常是调用方把"已经是像素"的点又乘了一次。与其画一张跑到
        # 画布外的掩膜（画面看上去"什么都没动"），不如当场响。
        raise EnhanceError(f"关键点不是归一化坐标：x 落在 [{lm[:, 0].min():.3f}, "
                           f"{lm[:, 0].max():.3f}]（enhance 要的是 face.py 那份 [0,1] 契约）")
    return np.stack([lm[:, 0] * float(w), lm[:, 1] * float(h)], axis=-1)


# ------------------------------------------------------------------ 星形栅格化
def _wrap(a: float) -> float:
    """把角度折回 (-π, π]。"""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a <= -math.pi:
        a += 2.0 * math.pi
    return a


def _star_ok(verts: np.ndarray, cx: float, cy: float, rays: int = STAR_RAYS) -> str | None:
    """多边形对中心是不是星形。是 → None；不是 → 一句能给人看的拒绝理由。

    栅格化只对星形多边形正确：非星形时某条射线穿出又穿入，插出来的边界会把凹进去那块
    当作内部收进来（唇弓凹口、被睫毛压住的眼裂都可能）。所以这里用显式的射线—边段求交
    数出来，而不是祈祷夹具好看——`_star_weight` 用的还是同一套求交，两道因此共用一份
    几何真值：校验说"是星形"与画出来的掩膜必然一致。
    """
    n = len(verts)
    dx = verts[:, 0] - cx
    dy = verts[:, 1] - cy
    rho = np.hypot(dx, dy)
    if float(rho.max()) <= 0.0:
        return "所有顶点与中心重合"
    ang = np.arctan2(dy, dx)
    step = np.array([_wrap(float(ang[(i + 1) % n] - ang[i])) for i in range(n)], dtype=np.float64)
    total = float(step.sum())
    if abs(abs(total) - 2.0 * math.pi) > 1e-6:
        return f"绕心一圈不成立（总角度 {math.degrees(total):.1f}°）"
    for k in range(rays):
        th = 2.0 * math.pi * k / rays
        ux, uy = math.cos(th), math.sin(th)
        hits = 0
        for i in range(n):
            ax, ay = float(dx[i]), float(dy[i])
            j = (i + 1) % n
            bx, by = float(dx[j]), float(dy[j])
            # 射线 P = t·U (t>0) 与线段 A+s(B-A) (0≤s≤1) 的交点，克莱默解：
            #   det = Dx·uy − Dy·ux,  t = (Dx·Ay − Dy·Ax)/det,  s = (ux·Ay − uy·Ax)/det
            # （s 的那一项第一次写成 `ax*uy − ay*ux` 时差一个负号，实测所有射线都交
            #  0 次、于是两只眼在真夹具上被整层拒——符号错的校验比没有校验更坏，因为它
            # 撒谎撒得很像话。下面这三行由 test_enhance 的射线用例钉住。）
            det = (bx - ax) * uy - (by - ay) * ux
            if abs(det) < 1e-12:
                continue
            s = (ux * ay - uy * ax) / det
            if s < 0.0 or s > 1.0:
                continue
            t = ((bx - ax) * ay - (by - ay) * ax) / det
            if t > 0.0:
                hits += 1
        if hits != 1:
            return f"第 {math.degrees(th):.0f}° 方向与边界交 {hits} 次（星形要恰好 1 次）"
    return None


def _star_weight(xs: np.ndarray, ys: np.ndarray, cx: float, cy: float,
                 verts: np.ndarray, feather: float) -> np.ndarray:
    """星形多边形的软覆盖度：内部趋 1，边界在 feather 宽度内渐变到 0。

    边界半径按"顶点极角升序 + 相邻顶点间线性插值"求。直边在极坐标里的真值是
    r(θ)=d/cos(θ−φ)，线性插值在相邻顶点夹角 Δθ 上有 (1−cos(Δθ/2)) 的内偏：本层顶点
    最大夹角约 45° → 0.8% 半径，比 feather 本身小一个量级，而这里要的是软掩膜不是剪影。
    """
    dxa = verts[:, 0] - cx
    dya = verts[:, 1] - cy
    ang = np.arctan2(dya, dxa)
    order = np.argsort(ang)
    ax, ay, a = dxa[order], dya[order], ang[order]
    n = int(len(a))
    # 每条边 i 的极角区间是 [a[i], a[i+1]]；末边补回第一个顶点（角度 +2π、坐标不变）
    bx = np.concatenate([ax[1:], ax[:1]])
    by = np.concatenate([ay[1:], ay[:1]])
    hi = np.concatenate([a[1:], [a[0] + 2.0 * math.pi]])
    theta = np.arctan2(ys - cy, xs - cx)
    theta = np.where(theta < a[0], theta + 2.0 * math.pi, theta)
    idx = np.clip(np.searchsorted(hi, theta, side="right"), 0, n - 1)
    ux, uy = np.cos(theta), np.sin(theta)
    ex, ey = bx[idx] - ax[idx], by[idx] - ay[idx]
    det = ex * uy - ey * ux
    with np.errstate(divide="ignore", invalid="ignore"):
        # 与 _star_ok 逐字同一套克莱默解：t 就是这条射线与该边段的真实交点距离
        t = (ex * ay[idx] - ey * ax[idx]) / det
    # det≈0（两顶点同角、边退化成径向）时退回该顶点半径；t≤0 表示边界在中心的**反**方向，
    # 也就是这个多边形对这中心不是星形——那时这一向半径记 0（整条射线不给额度），
    # 让本函数自己不依赖调用方那道 _star_ok 也不会画出假凸起。
    t = np.where(np.abs(det) < 1e-12, np.hypot(ax[idx], ay[idx]), t)
    rb = np.where(t > 0.0, t, 0.0)
    rho = np.hypot(xs - cx, ys - cy)
    if feather <= 0.0:
        return (rho <= rb).astype(np.float64)
    return np.clip((rb - rho) / feather + 0.5, 0.0, 1.0)


def _disc_weight(xs, ys, cx, cy, r: float, edge: float) -> np.ndarray:
    """圆盘软覆盖度（虹膜）：半径 r，边界渐变宽度 edge。"""
    rho = np.hypot(xs - cx, ys - cy)
    if edge <= 0.0:
        return (rho <= r).astype(np.float64)
    return np.clip((r - rho) / edge + 0.5, 0.0, 1.0)


def _ramp_down(x, hi: float, span: float) -> np.ndarray:
    """"比 hi 淡"的门：x ≤ lo 给 1、x ≥ hi 给 0，中间 smoothstep（硬阈值会留接缝）。"""
    lo = max(0.0, hi * span)
    if hi <= lo:
        return np.zeros_like(x)
    return 1.0 - smoothstep(x, lo, hi)


def _ramp_up(x, lo: float, hi: float) -> np.ndarray:
    """"比 lo 亮/艳"的门。lo≥hi 视为门不可用 → 全 0（而不是全 1 蒙过去）。"""
    if hi <= lo:
        return np.zeros_like(x)
    return smoothstep(x, lo, hi)


# ---------------------------------------------------------------------- 几何场
@dataclass
class Regions:
    """几何掩膜场（还没过内容门）。window 是它在画布上的那一片。"""

    weight: np.ndarray              # (3,fh,fw) float32 [0,1]，顺序 = SUBS
    window: tuple                   # (y0, x0, fh, fw)
    canvas: tuple                   # (h, w)
    info: dict = field(default_factory=dict)


def geometry(landmarks, h: int, w: int) -> Regions:
    """从 478 点画三张几何掩膜（眼白 / 虹膜 / 牙齿）。只碰几何，不碰像素。

    不支持的情形（侧脸到唇环不再星形、虹膜小过一档、嘴闭上）在这里就**显式**留下
    reason，而不是画一张"看上去像"的掩膜：reason 随 refine() 与事件一路带出去。
    """
    h = int(h)
    w = int(w)
    if h <= 0 or w <= 0:
        raise EnhanceError(f"画布尺寸非法：{(h, w)}")
    lm = _landmark_pixels(landmarks, h, w)

    # 羽化宽度先算，因为它决定窗口要多大——顺序反了就等于允许软边被窗口边界硬切一刀。
    feather_eye = 0.0
    for iris, rim in ((IRIS_LEFT, IRIS_RIM_LEFT), (IRIS_RIGHT, IRIS_RIM_RIGHT)):
        r_pre = float(np.hypot(lm[list(rim), 0] - float(lm[iris, 0]),
                               lm[list(rim), 1] - float(lm[iris, 1])).mean())
        feather_eye = max(feather_eye, max(1.0, EYE_FEATHER_OF_IRIS * r_pre))
    mouth_w = float(math.hypot(float(lm[MOUTH_CORNER_RIGHT, 0] - lm[MOUTH_CORNER_LEFT, 0]),
                               float(lm[MOUTH_CORNER_RIGHT, 1] - lm[MOUTH_CORNER_LEFT, 1])))
    feather_mouth = max(1.0, LIP_FEATHER_OF_MOUTH_W * mouth_w)
    # `_star_weight` 在 rb + feather/2 处归零，所以窗口至少要比包围盒每边宽 feather/2；
    # 再留 1 px 给像素中心与格点的半步偏移。
    pad = max(REGION_PAD_PX, 0.5 * max(feather_eye, feather_mouth) + 1.0)

    # 窗口按几何顶点的包围盒 + pad 定。三张掩膜画在同一块窗口上，于是预览与导出都只
    # 带这一小块，而不是整幅画布的掩膜。
    allv = np.concatenate([lm[list(EYE_RING_LEFT)], lm[list(EYE_RING_RIGHT)],
                           lm[list(LIP_CHAIN_UPPER)], lm[list(LIP_CHAIN_LOWER)]])
    x0 = max(0.0, float(allv[:, 0].min()) - pad)
    x1 = min(float(w), float(allv[:, 0].max()) + pad)
    y0 = max(0.0, float(allv[:, 1].min()) - pad)
    y1 = min(float(h), float(allv[:, 1].max()) + pad)
    iy0, ix0 = int(math.floor(y0)), int(math.floor(x0))
    iy1, ix1 = min(h, int(math.ceil(y1))), min(w, int(math.ceil(x1)))
    fh, fw = max(1, iy1 - iy0), max(1, ix1 - ix0)
    yy, xx = np.mgrid[iy0:iy0 + fh, ix0:ix0 + fw]
    xs = np.clip(xx.astype(np.float64) + 0.5, 0.0, w - 1.0)
    ys = np.clip(yy.astype(np.float64) + 0.5, 0.0, h - 1.0)

    weight = np.zeros((3, fh, fw), dtype=np.float32)
    info: dict = {"eyes": [], "mouth": {}}

    for ring, iris, rim in ((EYE_RING_LEFT, IRIS_LEFT, IRIS_RIM_LEFT),
                            (EYE_RING_RIGHT, IRIS_RIGHT, IRIS_RIM_RIGHT)):
        verts = lm[list(ring)]
        cx, cy = float(lm[iris, 0]), float(lm[iris, 1])
        r_iris = float(np.hypot(lm[list(rim), 0] - cx, lm[list(rim), 1] - cy).mean())
        rec: dict = {"center": [round(cx, 1), round(cy, 1)], "iris_r_px": round(r_iris, 2)}
        bad = _star_ok(verts, cx, cy)
        if bad is None and r_iris < EYE_IRIS_R_MIN:
            bad = f"虹膜半径 {r_iris:.2f} px < {EYE_IRIS_R_MIN}，画不出可信的圆盘"
        if bad is not None:
            rec["reject"] = bad
            info["eyes"].append(rec)
            continue
        feather = max(1.0, EYE_FEATHER_OF_IRIS * r_iris)
        eye = _star_weight(xs, ys, cx, cy, verts, feather)
        disc = _disc_weight(xs, ys, cx, cy, r_iris, max(1.0, 0.22 * r_iris))
        # 虹膜只在眼裂里：被眼睑盖住的那半不许增强（那正是"越界"最常见的形状）
        weight[0] = np.maximum(weight[0], eye * (1.0 - disc))
        weight[1] = np.maximum(weight[1], disc * eye)
        rec["eye_px"] = int((eye > 0.5).sum())
        rec["iris_px"] = int(((disc * eye) > 0.5).sum())
        rec["sclera_px"] = int(((eye * (1.0 - disc)) > 0.5).sum())
        info["eyes"].append(rec)

    # 唇外环 = 上链正向 + 下链反向（去掉重复的两个嘴角）；中心取嘴角中点。
    ring = list(LIP_CHAIN_UPPER) + list(LIP_CHAIN_LOWER)[-2:0:-1]
    verts = lm[ring]
    cx = float(lm[MOUTH_CORNER_LEFT, 0] + lm[MOUTH_CORNER_RIGHT, 0]) / 2.0
    cy = float(lm[MOUTH_CORNER_LEFT, 1] + lm[MOUTH_CORNER_RIGHT, 1]) / 2.0
    gap = float(lm[LIP_INNER_BOTTOM, 1] - lm[LIP_INNER_TOP, 1])
    open_ = gap / mouth_w if mouth_w > 0 else 0.0
    minfo: dict = {"mouth_w_px": round(mouth_w, 1), "lip_gap_px": round(gap, 1),
                   "openness": round(open_, 4)}
    info["mouth"] = minfo
    if mouth_w <= 4.0:
        minfo["reject"] = f"嘴宽只有 {mouth_w:.1f} px，画不出可信的牙齿掩膜"
    else:
        bad = _star_ok(verts, cx, cy)
        if bad is not None:
            minfo["reject"] = f"唇环对唇心不是星形：{bad}"
        else:
            feather = max(1.0, LIP_FEATHER_OF_MOUTH_W * mouth_w)
            lips = _star_weight(xs, ys, cx, cy, verts, feather)
            # 竖直带：内唇上下两点定出的开口带（上下各外扩 15% 间距 + 一个羽化宽度）。
            # 牙齿只能在这条带里——这一格把"唇面高光"挡在掩膜之外的作用比内容门还大。
            band = max(1.0, gap) * 0.15 + feather
            y_top = min(float(lm[LIP_INNER_TOP, 1]), float(lm[LIP_INNER_BOTTOM, 1]))
            y_bot = max(float(lm[LIP_INNER_TOP, 1]), float(lm[LIP_INNER_BOTTOM, 1]))
            soft = np.clip(np.minimum(y_bot + band - ys, ys - (y_top - band)) / max(feather, 1.0)
                           + 0.5, 0.0, 1.0)
            teeth = lips * soft
            weight[2] = np.maximum(weight[2], teeth.astype(np.float32))
            minfo["lips_px"] = int((lips > 0.5).sum())
            minfo["teeth_geom_px"] = int((teeth > 0.5).sum())
            if open_ < MOUTH_OPEN_MIN:
                minfo["reject"] = (f"开口度 {open_:.3f} < {MOUTH_OPEN_MIN}（13/14 只差 "
                                   f"{gap:.1f} px）：这是闭嘴样本，牙齿那一格不会点火")

    return Regions(weight=weight, window=(iy0, ix0, fh, fw), canvas=(h, w), info=info)


# ------------------------------------------------------------------- 内容门与统计
def _pool_mean(a: np.ndarray, m: np.ndarray) -> float:
    tot = float(m.sum())
    if tot <= 0.0:
        return 0.0
    return float((a * m).sum() / tot)


def refine(reg: Regions, src: np.ndarray) -> tuple[np.ndarray, dict]:
    """把几何场削成最终权重：每子功能一道相对内容门。返回 (weight, 一手事实账)。

    src 是窗口那一片 (fh,fw,3) 的 float [0,1]，取的是**源片**那份颜色（模块头写了
    为什么不能用屏幕上的颜色）。算完这一次，每帧只按权重做逐点乘加。
    """
    src = np.asarray(src, dtype=np.float64)
    fh, fw = int(reg.weight.shape[1]), int(reg.weight.shape[2])
    if src.ndim != 3 or src.shape[:2] != (fh, fw) or src.shape[2] != 3:
        raise EnhanceError(f"refine 要的窗口像素是 ({fh},{fw},3)，得到 {src.shape}")
    if not np.isfinite(src).all():
        raise EnhanceError("窗口像素含非有限值，整层拒绝")
    hsv = rgb_to_hsv_np(np.clip(src, 0.0, 1.0))
    s, v = hsv[..., 1], hsv[..., 2]
    out = np.array(reg.weight, dtype=np.float32)
    facts: dict = {}

    # 虹膜盘是眼白门的基准。两只眼都被拒时没有基准 → 眼白整层不点火并写明原因，
    # 而不是退化成"随便找个绝对阈值"：那是把不可信的一层伪装成可用。
    s_iris = _pool_mean(s, reg.weight[1])
    v_sclera = _pool_mean(v, reg.weight[0])
    s_sclera = _pool_mean(s, reg.weight[0])
    if s_iris > 0.0 and float(reg.weight[0].max()) > 0.0:
        gate = _ramp_down(s, s_iris * SCLERA_S_OF_IRIS, SCLERA_S_SPAN)
        if v_sclera > 0.0:
            gate = gate * _ramp_up(v, v_sclera * SCLERA_V_OF_POOL, v_sclera * SCLERA_V_SPAN)
        out[0] = (out[0] * gate).astype(np.float32)
        why = None
    else:
        out[0] = np.zeros_like(out[0])
        why = ("没有可用的虹膜基准（两只眼都被几何校验拒了）"
               if s_iris <= 0.0 else "眼白几何区一个像素也没有")
    facts["sclera"] = {"geom_px": int((reg.weight[0] > 0.5).sum()),
                       "gated_px": int((out[0] > 0.5).sum()),
                       "dropped_px": int(((reg.weight[0] > 0.5) & (out[0] <= 0.5)).sum()),
                       "pool_s_mean": round(s_sclera, 4), "pool_v_mean": round(v_sclera, 4),
                       "iris_s_mean": round(s_iris, 4), "reason": why}

    if s_iris > 0.0:
        # 虹膜门是**下界**：比盘面均值淡得多的不收（镜面高光、镜片反光、眼白渗进来）
        lo = s_iris * IRIS_S_OF_POOL
        out[1] = (out[1] * _ramp_up(s, lo, s_iris * IRIS_S_SPAN)).astype(np.float32)
        why = None
    else:
        out[1] = np.zeros_like(out[1])
        why = "没有虹膜几何区（两只眼都被几何校验拒了）"
    facts["iris"] = {"geom_px": int((reg.weight[1] > 0.5).sum()),
                     "gated_px": int((out[1] > 0.5).sum()),
                     "dropped_px": int(((reg.weight[1] > 0.5) & (out[1] <= 0.5)).sum()),
                     "pool_s_mean": round(s_iris, 4), "reason": why}

    teeth_geom = reg.weight[2]
    s_cav = _pool_mean(s, teeth_geom)
    v_cav = _pool_mean(v, teeth_geom)
    open_ok = (reg.info.get("mouth") or {}).get("reject") is None
    if float(teeth_geom.max()) > 0.0 and s_cav > 0.0 and v_cav > 0.0 and open_ok:
        gate = _ramp_down(s, s_cav * TEETH_S_OF_POOL, TEETH_S_SPAN) \
            * _ramp_up(v, v_cav * TEETH_V_OF_POOL * TEETH_V_SPAN, v_cav * TEETH_V_OF_POOL)
        gated = teeth_geom * gate
    else:
        gated = np.zeros_like(teeth_geom)
    kept = int((gated > 0.5).sum())
    why = None
    if kept < TEETH_MIN_PX:
        gated = np.zeros_like(gated)
        why = ((reg.info.get("mouth") or {}).get("reject") or
               f"门后只剩 {kept} px（要 ≥{TEETH_MIN_PX}）：这一格不点火")
    out[2] = gated.astype(np.float32)
    facts["teeth"] = {"geom_px": int((teeth_geom > 0.5).sum()), "gated_px": kept,
                      "kept_px": int((out[2] > 0.5).sum()),
                      "dropped_px": int(((teeth_geom > 0.5) & (out[2] <= 0.5)).sum()),
                      "min_px_required": TEETH_MIN_PX, "mouth_open_ok": bool(open_ok),
                      "pool_s_mean": round(s_cav, 4), "pool_v_mean": round(v_cav, 4),
                      "reason": why}
    for i, k in enumerate(SUBS):
        facts[k]["field_max"] = round(float(out[i].max()), 4)
    if not np.isfinite(out).all():
        raise EnhanceError("内容门产出非有限值，整层拒绝")
    return out, facts


def build_field(landmarks, h: int, w: int, src_nhwc: np.ndarray) -> tuple:
    """一步到位：几何 + 内容门。返回 (window, weight, info, facts)。

    src_nhwc 是**整幅画布**的 (H,W,3) float [0,1]（导出通路上已经解码好的那一份）。
    会话侧不用这个入口：它从显存里只切窗口（见 vram.set_enhance），不搬整幅。
    """
    reg = geometry(landmarks, h, w)
    y0, x0, fh, fw = reg.window
    win = np.asarray(src_nhwc, dtype=np.float64)[y0:y0 + fh, x0:x0 + fw]
    weight, facts = refine(reg, win)
    return reg.window, weight, reg.info, facts


# ---------------------------------------------------------------------- 三个子效
def _triple(a: dict) -> tuple:
    return (a["sclera"], a["iris"], a["teeth"])


def _sub_effects(h_, s, v, w0, w1, w2, amounts):
    """三个子效的公共体（两臂调同一个函数，算式只有一份）。

    返回 (s_new, v_new)：h 不在这里出现一次——"色相零改动"是这条算式的结构事实，
    写成函数而不是写两遍，是为了让两臂不可能各自漂出一份。
    三个量都是**乘性**：饱和下降 `s·(1−d·a·w)`、饱和上升夹在 `max(s, 上限)` 下、
    明度上升夹在 `max(v, V_CEIL)` 下。乘性的好处除了保住层次，还有一条是本层的结构：
    s=0 的中性像素（眼镜框、高光、白墙）在三个式子里都恒等于自己，所以不会被"上色"。
    """
    a0, a1, a2 = _triple(amounts)
    s_new, v_new = s, v
    if a0 > 0.0:
        s_new = s_new * (1.0 - SCLERA_DESAT * a0 * w0)
        v_new = _cap_up(v_new * (1.0 + SCLERA_LIFT * a0 * w0), v_new, V_CEIL)
    if a1 > 0.0:
        s_new = _cap_up(s_new * (1.0 + IRIS_SAT * a1 * w1), s_new, IRIS_S_CEIL)
        v_new = _cap_up(v_new * (1.0 + IRIS_LIFT * a1 * w1), v_new, V_CEIL)
    if a2 > 0.0:
        s_new = s_new * (1.0 - TEETH_DESAT * a2 * w2)
        v_new = _cap_up(v_new * (1.0 + TEETH_LIFT * a2 * w2), v_new, V_CEIL)
    return s_new, v_new


def _cap_up(y, x, ceil: float):
    """`min(y, max(x, ceil))`：把推高后的 y 夹在“不越过天花板，也不把原值拉低”里。

    为什么不直接写 `min(y, ceil)`：x 本来就大于 ceil 时那会把用户的像素**往下拽**，
    而“过曝护栏”的职责是不再往上推，不是把已经亮的地方压暗（那会在牙齿上留下一块
    比原来更暗的高光，比过曝更难查）。torch 臂用 `torch.minimum(y, x.clamp_min(ceil))`，
    同一条式子。
    """
    return np.minimum(y, np.maximum(x, ceil))


def enhance_np(x: np.ndarray, weight: np.ndarray, amounts) -> np.ndarray:
    """解析真值臂：x 是 (fh,fw,3) 或 (…,fh,fw,3)，weight 是 (3,fh,fw)。

    混合写成 `x + (out − x)·wc`：wc=0 处它在 IEEE 下精确回到 x（`0·有限=0`），
    所以"掩膜外逐字节不变"不依赖任何浮点巧合。全零权重再叠一层结构短路。
    """
    a = check_amounts(amounts)
    x = np.asarray(x, dtype=np.float64)
    w = np.asarray(weight, dtype=np.float64)
    if w.ndim != 3 or w.shape[0] != 3 or w.shape[-2:] != x.shape[-3:-1]:
        raise EnhanceError(f"权重形状 {w.shape} 与窗口 {x.shape} 不合（要 (3,fh,fw)）")
    if is_identity(a):
        return x.copy()
    hsv = rgb_to_hsv_np(np.clip(x, 0.0, 1.0))
    s_new, v_new = _sub_effects(None, hsv[..., 1], hsv[..., 2],
                                np.clip(w[0], 0.0, 1.0), np.clip(w[1], 0.0, 1.0),
                                np.clip(w[2], 0.0, 1.0), a)
    eff = hsv_to_rgb_np(np.stack([hsv[..., 0], np.clip(s_new, 0.0, 1.0),
                                  np.clip(v_new, 0.0, 1.0)], axis=-1))
    # 混合权重只统计**点火了**的那几格。a=0 的子层对 `eff` 没有贡献（乘性式在 a=0 时
    # 恒等），把它的权重算进混合里就等于把 hsv 往返的 1e-17 舍入也混进画面：实测"只开
    # 牙齿"时有 114347 格眼白像素与源片差 1e-17——8bit 上看不见，16-bit 直通导出上就是
    # 一次真实改动，而"每子功能独立启停"要的正是逐字节。
    wc = np.clip(sum(w[i] for i, k in enumerate(SUBS) if a[k] > 0.0), 0.0, 1.0)[..., None]
    out = x + (eff - x) * wc
    if not np.isfinite(out).all():
        raise EnhanceError("眼牙增强产出非有限值，整层拒绝")
    return out


def enhance_t(t, weight_t, amounts):
    """生产内核：t 是窗口切片 (1,3,fh,fw)，weight_t 是 (3,fh,fw) 同设备 float。

    与 enhance_np 同一条算式（`_sub_effects` 的 torch 版在下面），两臂逐点一致由
    test_enhance 的对拍钉住。
    """
    if torch is None:
        raise RuntimeError("enhance_t 需要 torch")
    a = check_amounts(amounts)
    if t.ndim != 4 or t.shape[1] != 3:
        raise EnhanceError(f"enhance_t 需要 (N,3,H,W)，得到 {tuple(t.shape)}")
    if weight_t.shape != (3, t.shape[-2], t.shape[-1]):
        raise EnhanceError(f"权重 {tuple(weight_t.shape)} 与窗口 {tuple(t.shape)} 不合")
    if is_identity(a):
        return t                        # 结构短路：一个算子也不跑
    from .grade import hsv_to_rgb_t, rgb_to_hsv_t

    w0 = weight_t[0].unsqueeze(0).unsqueeze(0).clamp(0.0, 1.0)
    w1 = weight_t[1].unsqueeze(0).unsqueeze(0).clamp(0.0, 1.0)
    w2 = weight_t[2].unsqueeze(0).unsqueeze(0).clamp(0.0, 1.0)
    h_, s_, v_ = rgb_to_hsv_t(t.clamp(0.0, 1.0))
    s_new, v_new = _sub_effects_t(h_, s_.unsqueeze(1), v_.unsqueeze(1), w0, w1, w2, a)
    eff = hsv_to_rgb_t(h_, s_new[:, 0].clamp(0.0, 1.0), v_new[:, 0].clamp(0.0, 1.0))
    # 与 numpy 臂同式：只把点火了的那几格的权重算进混合（见 enhance_np 里那条注释）
    wc = sum(wi for wi, k in ((w0, "sclera"), (w1, "iris"), (w2, "teeth"))
             if a[k] > 0.0).clamp(0.0, 1.0)
    out = t + (eff - t) * wc
    if not torch.isfinite(out).all():
        raise EnhanceError("眼牙增强产出非有限值，整层拒绝（拦在写回之前）")
    return out


def _sub_effects_t(h_, s, v, w0, w1, w2, amounts):
    """torch 臂的子效。与 `_sub_effects` 逐句同式，只是运算符换成张量的。"""
    a0, a1, a2 = _triple(amounts)
    s_new, v_new = s, v
    if a0 > 0.0:
        s_new = s_new * (1.0 - SCLERA_DESAT * a0 * w0)
        v_new = torch.minimum(v_new * (1.0 + SCLERA_LIFT * a0 * w0), v_new.clamp_min(V_CEIL))
    if a1 > 0.0:
        s_new = torch.minimum(s_new * (1.0 + IRIS_SAT * a1 * w1), s_new.clamp_min(IRIS_S_CEIL))
        v_new = torch.minimum(v_new * (1.0 + IRIS_LIFT * a1 * w1), v_new.clamp_min(V_CEIL))
    if a2 > 0.0:
        s_new = s_new * (1.0 - TEETH_DESAT * a2 * w2)
        v_new = torch.minimum(v_new * (1.0 + TEETH_LIFT * a2 * w2), v_new.clamp_min(V_CEIL))
    return s_new, v_new


def report_guard(amounts_np_before, amounts_np_after):
    """给事件用的小工具：子功能级别的"这一格动了没有"。

    为什么单独有这一格：UI 的开关状态与画面事实必须能对上账。"三个数都是 0.4 而
    掩膜是空的"是一层没点火的层，事件里不把这点说清，面板就会替引擎说谎。
    """
    b = check_amounts(amounts_np_before)
    a = check_amounts(amounts_np_after)
    return {k: {"before": b[k], "after": a[k], "changed": b[k] != a[k]} for k in SUBS}
