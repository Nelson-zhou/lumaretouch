"""基于 478 点网格的 2D TPS 形变（M2-b：瘦脸 / 大眼 / 小下巴）。

为什么是 TPS 而不是"拿个椭圆往内压"：产品承诺的是**把某个点搬到某个位置**，其余地方
按薄板的连续形变过渡。TPS 是这族算法里唯一有闭式解、且形变处处平滑（C¹）的：
给定控制点 P 与请求位移 D，解

    [ U+λI   A ] [ w ]   [ D ]
    [ Aᵀ     0 ] [ a ] = [ 0 ]        U_ij = |p_i−p_j|² log|p_i−p_j|
                                           A = [1, pᵀ]（线性项 + Σw=Σw·p=0 约束）

然后稠密场 f(x) = Σ w_i U(|x−p_i|) + a₀ + a₁·x。线性项与两个约束条件不是装饰：
去掉之后整幅会带一个仿射分量，"只瘦左脸"会把背景一起平移。

四件事是探针（gpuspike/m2b2.py、m2b3.py）量出来的，不量就写就是猜：

1. **恒等网格必须逐字节还原**。align_corners=False 下像素 i 的中心归一化坐标是
   (2i+1)/h − 1，不是 linspace 的 ±(1−2/h)。后者把整幅重新采样了一遍（实测 98.8%
   像素变、最大 174 LSB），而前者实测 0 LSB。
2. **TPS 的边界锚点钉不住图像边缘**：锚点放在 0.02/0.98 时最外一圈仍有 3–11 px
   位移。所以稠密场还要乘一个紧支撑窗——瘦脸不该把背景拖走。
3. **稠密场必须在 GPU 上求值且必须 float64**：CPU numpy 在 672×848 上要 5.6 秒；
   而 float32 下 U(|x−p|) 的量级到 1e7，与 tiny 权重相乘是"大数相减得小数"，
   远场误差能到 1 px 级，正好毁掉第 2 条要保的"背景逐字节不动"。
4. **解算必须各向同性长度归一**（P/D/X 同除一个因子、场再乘回来）：不归一时 U 的
   元素到 1e7，λ=1e-8 相对它就是 7e-16——等于没正则，GPU 的 cusolver 与 LAPACK
   在这种条件数下差出 0.77 px（探针实测），而请求位移本身才 37 px。归一后 3.8e-6 px。

坐标约定（这一条被探针撞过两次，写死）：关键点入参是 face.py 契约里的**归一化**
[0,1] 代理帧坐标；本模块内部一律换算成**像素**，因为 U(r)=r²log r 只在各向同性的
长度下才是"薄板"——归一化空间里 W≠H 会把圆核拉成椭圆，"只瘦左脸"会带一个剪切分量。
紧支撑窗同样是像素空间的圆。对外暴露的位移场一律是 (1,H,W,2) 像素单位。

窗函数在 r ≤ r0 内恒为 1，所以控制点处的位移仍然是 TPS 精确插值的那个值；
r ≥ R 之外恒为 0，所以支撑是紧的、背景一个字节都不动。
"""

from __future__ import annotations

import math

import numpy as np

try:
    import torch
    import torch.nn.functional as F
except Exception:      # 与 ops.guided / ops.light 同一约定：CI 的 CPU job 没装 torch 也要能 import
    torch = None
    F = None

# MediaPipe Face Mesh 的 478 点拓扑里，本模块用到的那几组下标。
# 这是公开的事实性拓扑（点号→部位），不是任何上游代码；写死在这里是为了让
# "左脸往内收"这种语义有唯一解释——换后端时点位含义不能漂。
FACE_OVAL_LEFT = (234, 127, 162, 21, 54, 103, 67, 109)       # 太阳穴 → 下颌（左侧）
FACE_OVAL_RIGHT = (454, 399, 356, 288, 314, 405, 338, 308)   # 镜像
CHIN = 152
# 478 点版虹膜：468–472 左、473–477 右，其中 468/473 是中心，其余四个是上下左右边缘。
# 虹膜半径只从这里取：它是"大眼"唯一稳定的标尺——按脸宽归一的话，脸大脸小推出来的
# 视觉幅度不是一回事。
IRIS_LEFT = 468
IRIS_RIGHT = 473
IRIS_RIM_LEFT = (469, 470, 471, 472)
IRIS_RIM_RIGHT = (474, 475, 476, 477)
EYE_RING_LEFT = (33, 7, 163, 144, 145, 153, 154, 155)
EYE_RING_RIGHT = (263, 249, 390, 373, 374, 380, 381, 382)

KINDS = ("slim_face", "big_eye", "small_chin")
KIND_LIMIT = 1.0           # 滑块值域 [-1,1]；实际像素幅度由下面三个比例钉住

# 满档位移与脸部尺寸的比例。都以"脸"而不是"画面"为单位，换代理档、换构图才不变形。
# 数值取的是"推到顶明显但不过分卡通"的那一档，跑靶 m2-face-bench 把峰值位移钉在这里。
SLIM_PEAK_OF_FACE_W = 0.11    # 瘦脸：轮廓点最大内收 = 11% 脸宽（产品档约 26 px）
EYE_PEAK_OF_IRIS = 0.35       # 大眼：眼睑环外扩 = 35% 虹膜半径
CHIN_PEAK_OF_FACE_H = 0.055   # 小下巴：下巴尖上收 = 5.5% 脸高

# 窗的两个半径都以"脸半对角 R"为单位：r ≤ FLAT_RATIO·R 恒为 1（控制点全在这个圈里，
# 所以窗不改变 TPS 的插值精度），r ≥ SUPPORT_RATIO·R 恒为 0（紧支撑，背景不动）。
# 上一版给的是 1.35 / 0.62，算出来 r0 = 0.84R < R：控制点落在过渡带上，
# 探针实测瘦脸在控制点处差 13.4 px（请求 36.4 px）——窗把请求的位移自己削掉了。
SUPPORT_RATIO = 1.60
FLAT_RATIO = 1.05

# 图像边框上的零位移锚点。TPS 的线性项要靠它们把远场拉回 0；紧支撑窗是第二道防线。
BORDER_ANCHORS = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0),
                  (0.5, 0.0), (0.5, 1.0), (0.0, 0.5), (1.0, 0.5))


class DeformGeometryError(ValueError):
    """关键点几何不可用（数量不对、后端只给占位几何、单位不对）。整条命令必须拒绝。"""


def check_amounts(amounts) -> dict:
    """校验一组滑块值并返回干净副本：未知 kind / 非有限 / 越界都整条拒。

    单独拆出来而不是写在 set_deform_amounts 里，是为了让命令层能在**建层之前**
    先把参数把关：不然 `"slim_face": 5.0` 会先触发一次 55 ms 的解算、再在写值时
    被拒，留下一个“建了单但滑块全零”的会话——不致命，但上报与实际不一致。
    """
    if not isinstance(amounts, dict) or not amounts:
        raise ValueError("deform amounts 至少要给一个 kind")
    got = {}
    for k, v in amounts.items():
        if k not in KINDS:
            raise ValueError(f"未知形变类型 {k!r}（可用：{', '.join(KINDS)}）")
        a = float(v)
        if not math.isfinite(a) or abs(a) > KIND_LIMIT:
            raise ValueError(f"{k} 的形变量非法：{v!r}（需 |amount| ≤ {KIND_LIMIT} 的有限数）")
        got[k] = a
    return got


def analytic_frontal_landmarks(cx: float = 0.5, cy: float = 0.46, half_w: float = 0.19,
                               top: float = 0.27, bottom: float = 0.80,
                               eye_y: float = 0.42, eye_half: float = 0.075,
                               iris_r: float = 0.021) -> np.ndarray:
    """一张解析正脸的 478 点（归一化坐标）。**只给预热与测试夹具用**。

    它不是任何检测后端的输出，产品路径的关键点必须来自 precompute。之所以要有这么
    一个东西：预热要一份几何上合法的关键点才能把 grid_sample 那组内核跑起来，
    而拿真后端跑预热等于要求用户装一个带许可门禁的模型。

    脸形参数与探针 gpuspike/m2b4.py 一致：轮廓用抛物线包络而不是椭圆，因为椭圆
    在巴尖处 sin(π·1)=0 会把左右两侧收拢到同一个点上，slim_face 的请求因此互相抵消
    （上一版就在这上面误判过一次“算子错”）。
    """
    lm = np.zeros((478, 3), dtype=np.float32)
    placed = set()

    def put(i: int, x: float, y: float) -> None:
        lm[i] = [x, y, 0]
        placed.add(i)

    n = len(FACE_OVAL_LEFT)
    for side, idxs in ((-1.0, FACE_OVAL_LEFT), (1.0, FACE_OVAL_RIGHT)):
        for i, p in enumerate(idxs):
            t = i / (n - 1)
            put(p, cx + side * half_w * (1.0 - 0.82 * t * t), top + (bottom - top) * t)
    put(CHIN, cx, min(bottom + 0.02, 0.99))
    aspect = 1.0
    for iris, rim, ring, ex in ((IRIS_LEFT, IRIS_RIM_LEFT, EYE_RING_LEFT, cx - eye_half),
                                (IRIS_RIGHT, IRIS_RIM_RIGHT, EYE_RING_RIGHT, cx + eye_half)):
        put(iris, ex, eye_y)
        for q, (dx, dy) in zip(rim, ((1, 0), (0, -1), (-1, 0), (0, 1))):
            put(q, ex + dx * iris_r, eye_y + dy * iris_r * aspect)
        for k, p in enumerate(ring):
            a = k * math.pi / 4
            put(p, ex + 1.9 * iris_r * math.cos(a), eye_y + 1.9 * iris_r * math.sin(a) * aspect)
    # 剩下的点填在脸外接盒内的一个确定格子上。不填的话它们全在 (0,0)，而
    # face.py 的模板拟合是按“这份点集自己的外接盒”算缩放的——几个零会把整张脸
    # 推到画面左上角去。坐标用下标生成，所以对同一输入逐字节确定（不依赖 RNG）。
    rest = [i for i in range(478) if i not in placed]
    cols = 22
    rows = (len(rest) + cols - 1) // cols
    for k, i in enumerate(rest):
        gx = (k % cols) / (cols - 1)
        gy = (k // cols) / max(rows - 1, 1)
        put(i, (cx - half_w) + gx * 2 * half_w, top + gy * (bottom - top))
    return lm


def _check_points(landmarks) -> np.ndarray:
    """取 (478,2) 归一化关键点。数量不够直接拒——synthetic 后端给的是网格占位几何，
    拿它按脸形语义取点会搬到完全无关的位置上，且画面看起来"动了"，看不出错。"""
    lm = np.asarray(landmarks, dtype=np.float64)
    if lm.ndim != 2 or lm.shape[1] < 2 or lm.shape[0] < 478:
        raise DeformGeometryError(
            f"形变需要 478 点人脸网格，拿到 {lm.shape}：占位后端（synthetic）给的是网格"
            "几何，按脸形语义取点会搬到完全无关的位置，宁可拒绝")
    pts = lm[:, :2]
    # 单位约定也得当场拒：把像素坐标当归一化传进来（差 672 倍）不会报错，只会把
    # 整幅画面推到边界外去采样，border padding 之下得到一张"糊掉的棕块"。
    lo, hi = pts.min(), pts.max()
    if lo < -0.02 or hi > 1.02:
        raise DeformGeometryError(
            f"关键点值域 [{lo:.3f}, {hi:.3f}] 越出归一化 [0,1]：face.py 的契约是 x/y "
            "归一化到代理帧，传像素坐标请先除以 (w, h)")
    return pts


def support_radii(R: float) -> tuple[float, float]:
    """由脸半对角推出窗的两个半径（同一单位）。产品与测试都走它，不各自写字面量。"""
    return FLAT_RATIO * R, SUPPORT_RATIO * R


def face_frame(landmarks, h: int, w: int) -> tuple[float, float, float, float, float]:
    """(cx, cy, R, face_w, face_h)，全部**像素**单位。

    R 是脸轮廓到中心的最大像素距离（半对角），紧支撑窗以它为标尺；face_w / face_h
    是轮廓外接盒，三种形变的位移幅度以它为标尺。所有比例都相对"脸"而不是"画面"，
    换代理档、换构图时视觉幅度才一致。
    """
    pts = _check_points(landmarks)
    idx = list(FACE_OVAL_LEFT) + list(FACE_OVAL_RIGHT) + [CHIN]
    oval = pts[idx] * np.array([w, h], dtype=np.float64)
    cx, cy = float(oval[:, 0].mean()), float(oval[:, 1].mean())
    r = float(np.hypot(*(oval - np.array([cx, cy])).T).max())
    fw = float(oval[:, 0].max() - oval[:, 0].min())
    fh = float(oval[:, 1].max() - oval[:, 1].min())
    return cx, cy, max(r, 1e-6), max(fw, 1e-6), max(fh, 1e-6)


def dedupe_controls(P, D, tol: float = 0.5):
    """合并距离小于 tol 像素的控制点（位移取算术均值），返回 (P, D, 合并数)。

    为什么必须有：TPS 在一个位置只能有一个位移值。两张脸的下颌线在巴尖附近会几乎
    重合（本仓探针的参数化正脸就真的把左右两侧收在了同一个点上），左右各请求一个
    相反的水平位移时，带 λ 正则的解会把它压成 ~0 —— 不报错，只是"瘦脸推了没反应"。
    合并并计数，比让调用方去猜一个静默失效要诚实。

    计数按"每个保留点吸收了几个"算（写成 len(keep_d[i]) + 1 会恒为 3，因为那是个
    二维向量——上一版就是这么错的，合并数看着永远对不上）。
    """
    P = np.asarray(P, dtype=np.float64)
    D = np.asarray(D, dtype=np.float64)
    keep_p, keep_d, count, merged = [], [], [], 0
    for p, d in zip(P, D):
        for i, kp in enumerate(keep_p):
            if math.hypot(*(p - kp)) < tol:
                w_i = count[i] + 1
                keep_d[i] = (keep_d[i] * count[i] + d) / w_i
                count[i] = w_i
                merged += 1
                break
        else:
            keep_p.append(p)
            keep_d.append(d)
            count.append(1)
    return np.asarray(keep_p, dtype=np.float64), np.asarray(keep_d, dtype=np.float64), merged


def controls(landmarks, kind: str, amount: float, h: int, w: int,
             tol: float = 0.5) -> tuple[np.ndarray, np.ndarray, dict]:
    """返回 (P, D, meta)：控制点像素坐标、请求位移（像素）、以及合并了重数之类的元信息。

    像素单位是硬约定（理由见模块 docstring）。meta["merged"] 不为 0 时调用方应当上报——
    "左右下颌在巴尖重合"是真会发生的几何，静默合并等于把一半请求丢掉。
    """
    if kind not in KINDS:
        raise DeformGeometryError(f"未知形变类型 {kind!r}（可用：{', '.join(KINDS)}）")
    a = float(amount)
    if not math.isfinite(a) or abs(a) > KIND_LIMIT:
        raise DeformGeometryError(f"形变量非法：{amount!r}（需 |amount| ≤ {KIND_LIMIT} 的有限数）")
    pts = _check_points(landmarks)
    cx, cy, R, fw, fh = face_frame(landmarks, h, w)
    P, D = [], []
    if kind == "slim_face":
        # 左右轮廓按"越靠近中段推得越多"的正弦包络往内收；符号由 amount 决定，
        # 负值就是反向（丰颊），同一套点不需要第二份代码。
        for idxs, side in ((FACE_OVAL_LEFT, -1.0), (FACE_OVAL_RIGHT, 1.0)):
            n = len(idxs)
            for i, p in enumerate(idxs):
                env = math.sin(math.pi * (i + 1) / (n + 1))
                px, py = pts[p] * [w, h]
                P.append([px, py])
                D.append([side * SLIM_PEAK_OF_FACE_W * a * fw * env, 0.0])
    elif kind == "big_eye":
        for ring, iris, rim in ((EYE_RING_LEFT, IRIS_LEFT, IRIS_RIM_LEFT),
                                (EYE_RING_RIGHT, IRIS_RIGHT, IRIS_RIM_RIGHT)):
            ex, ey = pts[iris] * [w, h]
            ir = float(np.mean([math.hypot(*(pts[q] * [w, h] - np.array([ex, ey]))) for q in rim]))
            for p in ring:
                px, py = pts[p] * [w, h]
                vx, vy = px - ex, py - ey
                nrm = math.hypot(vx, vy) or 1.0
                P.append([px, py])
                step = EYE_PEAK_OF_IRIS * a * ir
                D.append([vx / nrm * step, vy / nrm * step])
    else:  # small_chin：下巴尖往上收，两侧下颌角各带一点，形成连续过渡
        for p, wgt in ((CHIN, 1.0), (FACE_OVAL_LEFT[4], 0.45), (FACE_OVAL_RIGHT[4], 0.45)):
            px, py = pts[p] * [w, h]
            P.append([px, py])
            D.append([0.0, -CHIN_PEAK_OF_FACE_H * a * fh * wgt])
        # 锚住下巴下方两点，否则整段下颌会跟着平移（TPS 的长尾）
        for p in (FACE_OVAL_LEFT[6], FACE_OVAL_RIGHT[6]):
            px, py = pts[p] * [w, h]
            P.append([px, py])
            D.append([0.0, 0.0])
    Pd, Dd, merged = dedupe_controls(np.asarray(P), np.asarray(D), tol=tol)
    # 边框锚点在合并之后追加：它们在图像四角，与脸上的点不可能重合，参与合并只会
    # 让 merged 这个数变得难以解释。
    for x, y in BORDER_ANCHORS:
        Pd = np.vstack([Pd, [[x * w, y * h]]])
        Dd = np.vstack([Dd, [[0.0, 0.0]]])
    return Pd, Dd, {"merged": int(merged), "n_controls": len(P),
                    "peak_px": float(np.abs(Dd).max()), "amount": a,
                    "frame": (cx, cy, R, fw, fh)}


def _u_kernel(d2):
    """U(r) = r²·log r，用 d²=|x−p|² 直接算：r²log r = ½·d²·log d²。
    d=0 处取 0（log 0 会炸，而 r²log r 的极限是 0）。"""
    if torch is not None and torch.is_tensor(d2):
        return 0.5 * d2 * torch.log(d2.clamp_min(1e-12))
    return 0.5 * d2 * np.log(np.maximum(d2, 1e-12))


def _tps_field(P, D, X, lam: float, scale: float = 1.0):
    """TPS 解算 + 在 X 上求稠密场。P/D/X 同制（numpy 或 float64 torch），像素单位。

    scale 是各向同性的长度归一（坐标与位移同除一个因子，场再乘回来）。见模块
    docstring 第 4 条：不做这一步，λ 相对 U 的量级等于 0，条件数会把 GPU/CPU 两条
    路径劈开近 1 px。
    """
    n = P.shape[0]
    is_t = torch is not None and torch.is_tensor(P)
    if scale != 1.0:
        P, D, X = P / scale, D / scale, X / scale
    if is_t:
        dev, dt = P.device, P.dtype
        A = torch.cat([torch.ones(n, 1, device=dev, dtype=dt), P], dim=1)
        L = torch.zeros(n + 3, n + 3, device=dev, dtype=dt)
        L[:n, :n] = _u_kernel(torch.cdist(P, P).pow(2))
        L[:n, n:] = A
        L[n:, :n] = A.T
        rhs = torch.zeros(n + 3, D.shape[1], device=dev, dtype=dt)
        rhs[:n] = D
        sol = torch.linalg.solve(L + lam * torch.eye(n + 3, device=dev, dtype=dt), rhs)
        aff = sol[n:]                             # (3,2)：aff[m, c] = 第 m 个基函数对第 c 个分量的系数
        # 注意是 X @ aff[1:] 而不是 X @ aff[1:].T：aff[1:] 的行是基函数（∂x、∂y）、列是
        # 分量，转置会把"x 基对 y 分量的系数"当成"y 基对 x 分量的系数"用。这个矩阵
        # 一般不对称，写错就是纯 y 请求里冒出 1 px 级的 x 位移（探针实测 1.19 px）。
        f = _u_kernel(torch.cdist(X, P).pow(2)) @ sol[:n] + aff[0] + X @ aff[1:]
    else:
        Pn, Dn, Xn = np.asarray(P), np.asarray(D), np.asarray(X)
        A = np.hstack([np.ones((n, 1)), Pn])
        L = np.zeros((n + 3, n + 3))
        L[:n, :n] = _u_kernel(((Pn[:, None, :] - Pn[None, :, :]) ** 2).sum(-1))
        L[:n, n:] = A
        L[n:, :n] = A.T
        rhs = np.zeros((n + 3, Dn.shape[1]))
        rhs[:n] = Dn
        sol = np.linalg.solve(L + lam * np.eye(n + 3), rhs)
        aff = sol[n:]                              # (3,2)：常数项 + 线性项，同上（不要转置）
        f = _u_kernel(((Xn[:, None, :] - Pn[None, :, :]) ** 2).sum(-1)) @ sol[:n] \
            + aff[0] + Xn @ aff[1:]
    return f * scale if scale != 1.0 else f


def _window(h: int, w: int, cx: float, cy: float, R: float, r0: float, tensor=None):
    """紧支撑窗：r ≤ r0 恒为 1，r ≥ R 恒为 0，中间 smoothstep。像素单位、各向同性的圆。
    控制点都落在 r0 内，所以窗不改变"TPS 精确插值请求位移"这条性质。"""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    r = np.hypot(xs - cx, ys - cy)
    t = np.clip((r - r0) / max(R - r0, 1e-9), 0.0, 1.0)
    win = 1.0 - t * t * (3.0 - 2.0 * t)
    if tensor is not None:
        win = torch.as_tensor(win, device=tensor, dtype=torch.float64)
    return win


def tps_field_np(P, D, h: int, w: int, *, cx: float, cy: float,
                 R: float, r0: float, lam: float = 1e-8) -> np.ndarray:
    """CPU 参考实现：返回 (H,W,2) 位移场（像素单位），带紧支撑窗。

    cx/cy/R/r0 都是像素单位，且必须是同一个坐标系（由 controls() 的 meta["frame"] 给）。
    这里不设默认值：默认值等于"猜一个脸的位置"，而脸在不在画面正中是后端说了算的事。
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    X = np.stack([xx.ravel(), yy.ravel()], axis=1)
    f = _tps_field(np.asarray(P, dtype=np.float64), np.asarray(D, dtype=np.float64),
                   X, lam, scale=float(max(h, w))).reshape(h, w, 2)
    return f * _window(h, w, cx, cy, R, r0)[..., None]


def tps_field_t(P, D, h: int, w: int, *, cx: float, cy: float,
                R: float, r0: float, lam: float = 1e-8, device="cpu"):
    """GPU 生产实现，与 tps_field_np 逐句同语义。float64 不是保守，是必需：
    U 的量级到 1e7，float32 下远场是"大数相减得小数"，误差能到 1 px 级。"""
    if torch is None:
        raise RuntimeError("tps_field_t 需要 torch")
    dev = torch.device(device) if isinstance(device, str) else device
    P64 = P.to(dev, dtype=torch.float64) if torch.is_tensor(P) else torch.as_tensor(P, dtype=torch.float64, device=dev)
    D64 = D.to(dev, dtype=torch.float64) if torch.is_tensor(D) else torch.as_tensor(D, dtype=torch.float64, device=dev)
    yy, xx = torch.meshgrid(
        torch.arange(h, device=dev, dtype=torch.float64),
        torch.arange(w, device=dev, dtype=torch.float64), indexing="ij")
    X = torch.stack([xx.ravel(), yy.ravel()], dim=1)
    f = _tps_field(P64, D64, X, lam, scale=float(max(h, w))).reshape(h, w, 2)
    win = _window(h, w, cx, cy, R, r0, tensor=dev)
    return (f * win[..., None]).to(torch.float32)


def unit_field(landmarks, kind: str, h: int, w: int, *, device="cpu",
               lam: float = 1e-8) -> tuple["torch.Tensor", dict]:
    """amount=1 时的位移场 (1,H,W,2) float32。产品只缓存这一份，拖滑块靠线性缩放。

    为什么能只存一份：TPS 的解对右端项 D 线性，而 D 与 amount 成正比，所以
    field(a) = a·field(1) 是**恒等**而不是近似（探针 m2b3 量到 ‖field(0.5) −
    0.5·field(1)‖max = 0.000e+00 px）。这条性质就是"滑块零推理"的全部依据；
    它一旦不成立，拖一下滑块就得重解一次 (n+3)×(n+3)，那是 34–79 ms。
    """
    P, D, meta = controls(landmarks, kind, 1.0, h, w)
    cx, cy, R, _fw, _fh = meta["frame"]
    r0, r1 = support_radii(R)
    t = tps_field_t(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0, lam=lam, device=device)
    return t[None], {"kind": kind, "controls": len(P), "merged": meta["merged"],
               "peak_px": round(meta["peak_px"], 3),
               "window": [round(cx, 2), round(cy, 2), round(R, 2), round(r0, 2), round(r1, 2)]}


def identity_grid(h: int, w: int, device="cpu", dtype=torch.float32 if torch is not None else None):
    """align_corners=False 的精确恒等网格：像素中心 (2i+1)/n − 1。
    写成 linspace(−1+2/n, 1−2/n, n) 会把整幅重新采样（实测 98.8% 像素变、174 LSB）。"""
    ys = (2 * torch.arange(h, device=device, dtype=dtype) + 1) / h - 1
    xs = (2 * torch.arange(w, device=device, dtype=dtype) + 1) / w - 1
    gy, gx = torch.meshgrid(ys, xs, indexing="ij")
    return torch.stack([gx, gy], dim=-1)[None]


def compose_grid(base, fields, amounts):
    """grid = base + Σ amount_k · field_k。空层直接返回 base（不额外分配）。

    这一步是每帧唯一做的事：没有 TPS 解算、没有 H2D。fields 是 unit_field 的产物，
    amounts 是滑块值。
    """
    if not fields:
        return base
    acc = None
    for f, a in zip(fields, amounts):
        if a == 0.0:
            continue
        acc = f * a if acc is None else acc + f * a
    if acc is None:
        return base
    return base + acc


def warp_t(img, delta, strength: float = 1.0, base=None):
    """按 base + strength·delta 采样。delta 是 (1,H,W,2) **像素**单位的位移场。

    像素→归一化的换算系数是 2/W、2/H（align_corners=False 下像素中心间隔就是这两个数），
    不能直接把像素加到归一化网格上：那样 18 px 的位移会变成 18 个归一化单位（=整幅
    超出边界），grid_sample 在 border padding 下把脸糊成一片边缘色。这个错不会
    被“恒等网格逐字节还原”抓到（s=0 时两边都是恒等），所以必须另有一条“平移 k 像素
    就得恰好搬 k 像素”的判据钉着——在 warp_np 里（它直接吃像素坐标）。

    strength=0 或空场直接返回入参：恒等网格实测逐字节还原，但那是一条依赖
    float32 舍入的经验性质，而"没推滑块⇒画面一个字节都不动"是产品承诺，
    不能建在经验上（M2-a2 的零增益区就是同样的形状）。
    """
    if torch is None:
        raise RuntimeError("warp_t 需要 torch")
    s = float(strength)
    if not math.isfinite(s) or abs(s) > KIND_LIMIT:
        raise ValueError(f"形变强度非法：{strength!r}（需 |strength| ≤ {KIND_LIMIT} 的有限数）")
    if delta is None or s == 0.0 or not bool(torch.any(delta)):
        return img
    h, w = img.shape[-2], img.shape[-1]
    grid = (identity_grid(h, w, img.device) if base is None else base) \
        + s * delta * torch.tensor([2.0 / w, 2.0 / h], device=delta.device, dtype=delta.dtype)
    out = F.grid_sample(img, grid.to(img.dtype), mode="bilinear",
                        padding_mode="border", align_corners=False)
    # 位移恰好为零的像素直接取原值：把"背景逐字节不动"从经验性质变成结构性质
    return torch.where((delta == 0).all(dim=-1)[None], img, out)


def warp_np(img, delta, strength: float = 1.0):
    """CPU 参考双线性采样，与 warp_t 同语义（含零位移区取原值）。"""
    s = float(strength)
    if not math.isfinite(s) or abs(s) > KIND_LIMIT:
        raise ValueError(f"形变强度非法：{strength!r}（需 |strength| ≤ {KIND_LIMIT} 的有限数）")
    a = np.asarray(img, dtype=np.float64)
    d = np.asarray(delta, dtype=np.float64)
    if d is None or s == 0.0 or not d.any():
        return img
    ch, H, W = a.shape[-3:]          # 入参约定：(...,C,H,W)
    src = a.reshape(-1, ch, H, W)
    g = d.reshape(1, H, W, 2).astype(np.float64) * s
    xs = (np.arange(W, dtype=np.float64)[None, :] + g[0, :, :, 0]).ravel()
    ys = (np.arange(H, dtype=np.float64)[:, None] + g[0, :, :, 1]).ravel()
    xs = np.clip(xs, 0.0, W - 1.0)
    ys = np.clip(ys, 0.0, H - 1.0)
    x0, y0 = np.floor(xs).astype(np.int64), np.floor(ys).astype(np.int64)
    x1, y1 = np.minimum(x0 + 1, W - 1), np.minimum(y0 + 1, H - 1)
    wx, wy = (xs - x0)[None, :], (ys - y0)[None, :]
    out = np.empty_like(src)
    for c in range(ch):
        plane = src[0, c]
        v = ((plane[y0, x0] * (1 - wx) * (1 - wy) + plane[y0, x1] * wx * (1 - wy)
              + plane[y1, x0] * (1 - wx) * wy + plane[y1, x1] * wx * wy))
        out[0, c] = v.reshape(H, W)
    zero = (d == 0).all(axis=-1).reshape(1, H, W)
    out = np.where(zero[:, None], src, out)
    return out.reshape(a.shape).astype(img.dtype)
