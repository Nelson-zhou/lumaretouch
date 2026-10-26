"""挑图建议（LNX-PICK-001）：代理像素度量与模型眼睑几何，仅供人工复核。

2026-10-25 v3 更正：以下旧标定笔记不是原片焦点/曝光质量验收；哈希已改为
固定64位，旧阈值仅为未重新标定的候选线。FaceMesh本身是模型，不宣称全路径无AI。

为什么这一份不叫「AI 挑图」：DoD §2 明令「严禁假滑块、假滤镜或伪装 AI」。官网那套挑图
是训练出来的分类器（10 种场景、正脸偏好、闭眼识别……），我们没有那种权重，也不打算
为凑一个功能名去下一份不可审计的模型。所以这里做的是**能被任何人复算的测量**，并把
每一格的算法名、数值、阈值原样报出去（手册 §AI挑图 的规则项：闭眼/欠曝/过曝/模糊 +
重复敏感度）：

· 近似组：dHash 64 位（16×16 灰度缩到 9×8 的相邻列梯度）→ 汉明距离。
  **手册 2127 行写明「相似分组不是绝对重复判定」**，所以这里给的是「像」与距离读数，
  从不写「重复图，删掉」。
· 模糊：两个条件同时成立才打标记（见 `clarity`）。单靠拉普拉斯方差的绝对值会冤枉
  「整体欠曝的好照片」——标定台上压暗 0.35× 的读数 0.001417 比明显糊的 0.005476 还低。
· 欠曝/过曝：亮度直方图两端的**裁切占比**（Rec.601 luma）。它量的是「死黑/死白」，
  不是「这张偏暗」——这句话写进 reason，否则用户会以为判据在替他决定曝光偏好。
· 疑似闭眼：MediaPipe FaceMesh 478 点的**眼睑几何**——上下睑中点像素距离除以眼裂
  像素宽度，两只眼取小值。用的是随包的 FaceMesh（Apache 2.0），但它是量出来的距离，
  不是训练出来的闭眼分类器；检测不到脸时如实报 unavailable，绝不退成「睁眼」。

全部阈值的出处：`packaging/pick-calibrate.py` 在同一份夹具上的实测读数（该脚本会把
判据指纹一起打出来）。每一档都在注释里写明它对应哪两个实测值之间的空档；夹具是
程序化画出来的脸，所以那些数只能定「方向」，不能当「真人阈值」——这句话写在用它们的
地方，而不是藏在实现里。

建议永远是**可覆盖的旁注**：它写进底片条那一格（与缩略图同一类派生物，不进工程文件、
不进撤销栈、不改源文件），用户自己的标签/标记/回收站永远赢，且这里没有任何一条路径
会删除或移动原片。
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

import numpy as np

from . import pick_group_eye as GE

SCHEMA = "lrt.pick.v1"
# 度量算到哪一版算法就记哪一版：同一张图在不同算法下数值不可比，台账要能分辨。
# v2 的分界是 `clarity` 多了「相对自身对比度」这一格（v1 只看绝对高频能量，会把
# 一张整体压暗的好照片报成糊图——标定台上实测错得很干脆）
ALGO_VERSION = "dhash-fixed9x8-area+proxy-clues-edge160+facemesh-eye-aperture-group-rule-v4"

# 缩略图/预览的公共尺度：所有像素类度量都在**长边固定**的这一档上算。
# 不换尺度不行：拉普拉斯方差随像素数直接变，一张 4000px 的锐图和一张 160px 的锐图
# 差两个数量级，阈值就成了「挑大图」而不是「挑清晰」。
MEASURE_EDGE = 160

# 重复敏感度（手册：重复 / 标准 / 相似）。64 位 dHash 上的汉明距离上限。
# 标定台实测（同一构图的不同张）：+2 偏置 0 位、高斯糊 r=3 1 位、整体压暗 0 位、
# 提亮 2.6× 14 位、裁掉 6 px 36 位。前三类都在 ≤6 里，所以「标准档 = 6」是量出来的；
# 提亮/裁切远开是哈希定义使然（构图变了），不是缺陷，也不许拿它当「不是同一张」。
DUPLICATE_SENSITIVITY = {"repeat": 3, "standard": 6, "similar": 10}
# 模糊敏感度：两个下限**同时**低于才算「疑似糊」（弱档最保守，只报最明显的）。
# 绝对高频能量（长边 160 上）实测锚点：真图 0.011579 / 轻糊 r=1.2 0.010145 /
# 明显糊 r=3.0 0.005476 / 纯色平坦 0.000000。
BLUR_SENSITIVITY = {"weak": 0.0040, "standard": 0.0060, "strong": 0.0090}
# 相对自身对比度（拉普拉斯方差 / 灰度方差）实测锚点：真图 0.2996 / 轻糊 0.2633 /
# 明显糊 0.1444 / **压暗 0.35× 0.2969**（这一条存在的全部理由：整体压暗时两个量按
# 同一个平方因子掉，比值不动，于是「暗」不再被读成「糊」）。
BLUR_RATIO_SENSITIVITY = {"weak": 0.10, "standard": 0.16, "strong": 0.22}
# 批内相对线：同一次分析里 ratio 的中位数乘这个系数，低于它的额外标「比同批其它张软」。
# 为什么还要这一条：绝对线跨图不可比（两张夹具的真图 ratio 分别是 0.30 与 0.52），
# 而挑图正是在「同一批连拍里挑那张糊的」这个场景里用的。实测：两人夹具真图 0.5177、
# 同一张糊 r=3.0 0.3099——绝对线抓不到它，批内线抓得到。
BLUR_REL_FACTOR = {"weak": 0.45, "standard": 0.55, "strong": 0.65}
# 画面自身的对比度下限（灰度标准差/255）：低于它就说「判据不适用」，不判糊也不判锐。
# 纯色与纯色+噪声两种极端实测：平坦 graystd=0.0000 ratio=0.0000，平坦+噪声
# graystd=0.00065 ratio=20.0（噪声把比值顶爆）。没有这一条，空白图会被判成糊图。
CONTRAST_FLOOR = 0.02
# 曝光敏感度：亮度裁剪占比上限（单侧）。欠曝=极暗占比，过曝=极亮占比。
# 实测锚点：真图 over=0.00010、提亮 2.6× over=0.85020、压暗 0.35× under=0.00049。
# 最后那一个数要如实读：**整张压暗并不会造出死黑裁切**，所以这一格报的是裁切而不是
# 「偏暗」——标准档 6% 落在 0.0001 与 0.85 之间，两侧都留出十倍的余量。
EXPOSURE_SENSITIVITY = {"weak": 0.12, "standard": 0.06, "strong": 0.03}
# 眼裂「睁开比」下限（两只眼取小值，像素尺度上的比值）。标定台实测：程序化单人夹具
# 睁开 0.4599、把眼区涂平后重检测 0.2279；两人夹具脸 1 睁开 0.4723 → 涂平 0.2329，
# 而脸 0 涂平后 0.4642 → 0.4723（**没降**：那个变体在这一张脸上没造出闭眼，如实留着
# 当反面读数，不拿它当判据）。公开 EAR 文献里真人闭眼 <0.15、睁眼 0.25–0.35，所以
# 强档 0.240 刚好把「画出来的闭眼替身」标出来，而真人小眼睛紧贴这条线上方——这就是
# 为什么这一条**只当「要不要复核」的标记**，数值与阈值一起报出去，不当结论。
# 再加一条实测：同一张涂平眼裂的图，在 512 档检测读到 0.21883、在满幅（1024）上读到
# 0.22795，差约 4%——检测尺度本身就给这个几何量带几个百分点的抖动。所以这一条只当
# 「要不要复核」的标记，数值与阈值一起报出去，绝不当结论（端到端用例把「两次跑逐字节
# 相同」与「两个尺度落在阈值同侧」分别钉住）。
# 拿画出来的脸当「真人闭眼阈值」的定标依据是不诚实的——这句话写在这里而不是藏在注释里。
EYE_SENSITIVITY = {"weak": 0.120, "standard": 0.165, "strong": 0.240}
DARK_CUTOFF = 8          # luma 下界（uint8）：≤ 它就是纯黑裁切
BRIGHT_CUTOFF = 247      # luma 上界：≥ 它就是纯白裁切

# FaceMesh 478 点的眼睑/眼裂编号。与 ops/deform.EYE_RING_* 是同一套编号约定
# （大眼形变用的就是这两圈轮廓），这里只取其中四个点做距离测量：
# 外/内眼角给「眼裂宽度」，上/下睑中点给「睁开的高度」。
EYE_LEFT = {"outer": 33, "inner": 133, "upper": 159, "lower": 145}
EYE_RIGHT = {"inner": 362, "outer": 263, "upper": 386, "lower": 374}


@dataclass
class Measures:
    """一张图的全部读数（没有一个字段是「结论」，结论在 suggest() 里合成）。"""

    path: str
    dhash: int = 0
    sharpness: float = 0.0          # 归一化拉普拉斯方差（绝对高频能量）
    ratio: float = 0.0              # 上式 / 灰度方差：对整体曝光不敏感的那一格
    contrast: float = 0.0           # 灰度标准差/255：画面自己有没有可比内容
    under: float = 0.0
    over: float = 0.0
    eye_open: float | None = None          # None = 没量到（没脸 / 没装后端）
    eye_note: str = ""
    faces: int = 0
    face_detection: dict = field(default_factory=dict)  # absent/failed is unknown, not census zero
    decoded_from: str = ""           # "decoded_proxy" / "camera_preview"：RAW 那一路必须说清
    decode_size: tuple = ()          # 度量时那份像素的尺寸（FaceMesh 就在这份上跑）
    source_size: tuple = ()
    source_stamp: list = field(default_factory=list)
    ms: dict = field(default_factory=dict)

    def for_json(self) -> dict:
        return {"dhash": f"{self.dhash:016x}", "sharpness": self.sharpness,
                "clarity_ratio": self.ratio, "contrast": self.contrast,
                "under": self.under, "over": self.over,
                "eye_open": (None if self.eye_open is None else self.eye_open),
                "eye_note": self.eye_note, "faces": int(self.faces),
                "face_detection": dict(self.face_detection),
                "decoded_from": self.decoded_from, "decode_size": list(self.decode_size),
                "source_size": list(self.source_size), "source_stamp": list(self.source_stamp),
                "quality_scope": "decoded-proxy-edge160-not-original-focus",
                "measure_edge": MEASURE_EDGE, "algo": ALGO_VERSION,
                "ms": {k: round(float(v), 2) for k, v in self.ms.items()}}


# ---------------------------------------------------------------- 像素类度量
def to_gray_measured(rgb: np.ndarray, edge: int = MEASURE_EDGE) -> np.ndarray:
    """降采样到长边 edge 的灰度图（float32, (h,w)）。

    缩放自己写而不调 PIL：这一步要在几百张图上跑，而结果必须与 Pillow 版本无关
    ——度量类函数一旦「看库脸色」，同一张图在两台机器上就会得到不同的挑图结论。
    这里用的是面积平均（整数块均值 + 最近邻收尾），足够稳，且完全可复算。
    """
    a = np.asarray(rgb)
    if a.ndim != 3 or a.shape[2] < 3:
        raise ValueError(f"要 (H,W,3) 的 RGB/灰度数组，得到 shape={a.shape}")
    h, w = int(a.shape[0]), int(a.shape[1])
    if max(h, w) <= 0:
        raise ValueError("空图像")
    # luma 先算（全分辨率上），再整块平均降采样：顺序反了会把三个通道的插值误差
    # 带进亮度里，而亮度是后面两个判据（曝光裁切、高频能量）的公共底
    g = (0.299 * a[:, :, 0].astype(np.float32) + 0.587 * a[:, :, 1].astype(np.float32)
         + 0.114 * a[:, :, 2].astype(np.float32))
    return _downscale_mean(g, edge)


def _downscale_mean(g: np.ndarray, edge: int) -> np.ndarray:
    """面积平均降采样到长边 = edge（纯 numpy，两步：整数块均值 → 最近邻收尾）。

    为什么不用 PIL/torch：这一步在几百张图上跑，而结果必须与库版本无关。度量函数
    一旦「看库脸色」，同一张图在两台机器上就会给出不同的挑图结论——那与假滤镜只差
    一句注释。**整数块均值**是这里的关键：直接按步长抽样会混叠，混叠会把高频能量
    虚假抬高，于是「糊图」读起来比「锐图」还锐。
    """
    h, w = int(g.shape[0]), int(g.shape[1])
    k = max(1, int(max(h, w) // edge))
    if k > 1:
        hh, ww = h - h % k, w - w % k
        if hh >= 1 and ww >= 1:
            g = g[:hh, :ww].reshape(hh // k, k, ww // k, k).mean(axis=(1, 3))
    h, w = int(g.shape[0]), int(g.shape[1])
    scale = float(edge) / float(max(h, w))
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    if (nh, nw) == (h, w):
        return g.astype(np.float32)
    ys = np.minimum((np.arange(nh) * h / nh).astype(int), h - 1)
    xs = np.minimum((np.arange(nw) * w / nw).astype(int), w - 1)
    return g[ys][:, xs].astype(np.float32)


def _area_grid(g: np.ndarray, height: int, width: int) -> np.ndarray:
    """Fixed grid, independent of aspect ratio; exact fractional pixel-area weights.

    This is our existing NumPy measurement path, not a vendored ImageHash resize.
    Separability keeps allocations bounded by the already-small measured image.
    """
    def weights(src, dst):
        left = np.arange(dst, dtype=np.float64)[:, None] * src / dst
        right = (np.arange(dst, dtype=np.float64)[:, None] + 1) * src / dst
        pixels = np.arange(src, dtype=np.float64)[None, :]
        return np.maximum(0, np.minimum(right, pixels + 1) - np.maximum(left, pixels)) / (src / dst)
    return weights(g.shape[0], height) @ g @ weights(g.shape[1], width).T


def dhash64(rgb: np.ndarray) -> int:
    """Exactly 8 rows × 8 horizontal differences, for every input aspect ratio.

    A low distance is only a composition clue. Tone, crop, rotation, mirrors and
    low-information frames can collide or diverge; this never proves duplicates.
    """
    small = _area_grid(to_gray_measured(rgb), 8, 9)
    bits = 0
    for value in (small[:, 1:] > small[:, :-1] + 1e-9).reshape(-1):
        bits = (bits << 1) | int(bool(value))
    return bits


def source_stamp(path: str) -> list[int]:
    """Best-effort local file identity/change fence, NOT a content digest."""
    st = os.stat(path)
    return [int(st.st_dev), int(st.st_ino), int(st.st_size),
            int(st.st_mtime_ns), int(st.st_ctime_ns)]


def source_owners(rows, session):
    """Freeze the first source publisher's exact row/document/workspace identity."""
    result = {}
    for row in rows:
        path = row['path']
        if path not in result:
            result[path] = {'row': row, 'path': path, 'document_id': row.get('document_id'),
                            'session': session}
    return result


def owner_index(rows, session, owner):
    """Never substitute a same-path or same-document-ID replacement row."""
    if not owner or owner['session'] != session:
        return -1
    row = owner['row']
    if row.get('path') != owner['path'] or row.get('document_id') != owner['document_id']:
        return -1
    return next((i for i, candidate in enumerate(rows) if candidate is row), -1)


def reusable(suggestion, path: str, edge: int, sensitivities: dict, model_dir=None) -> bool:
    """Never combine old hash definitions, decoder scales or replaced sources."""
    if not isinstance(suggestion, dict):
        return False
    mm = suggestion.get("measures") or {}
    if (suggestion.get("fingerprint") != fingerprint()
            or suggestion.get("edge") != edge
            or suggestion.get("sensitivities") != sensitivities
            or suggestion.get("model_dir") != model_dir
            or mm.get("algo") != ALGO_VERSION):
        return False
    try:
        if mm.get("source_stamp") != source_stamp(path):
            return False
        # Verified detection is tied to actual model bytes, not only its directory.
        return not mm.get("face_detection") or GE.current(restore_measures(path, mm)) is not None
    except (OSError, KeyError, TypeError, ValueError):
        return False


def restore_measures(path: str, value: dict) -> Measures:
    """Restore only an already-fenced current-version in-memory measurement."""
    return Measures(path=path, dhash=int(value["dhash"], 16),
                    sharpness=value["sharpness"], ratio=value["clarity_ratio"],
                    contrast=value["contrast"], under=value["under"], over=value["over"],
                    eye_open=value["eye_open"], eye_note=value.get("eye_note", ""),
                    faces=value["faces"], face_detection=dict(value.get("face_detection") or {}),
                    decoded_from=value["decoded_from"],
                    decode_size=tuple(value["decode_size"]), source_size=tuple(value["source_size"]),
                    source_stamp=list(value["source_stamp"]), ms=dict(value.get("ms", {})))


def hamming(a: int, b: int) -> int:
    return int(bin(int(a) ^ int(b)).count("1"))


def clarity(rgb: np.ndarray) -> dict:
    """清晰度那一格的三个读数：(绝对高频能量, 相对自身对比度, 自身对比度)。

    为什么不是一个数：拉普拉斯方差**按对比度的平方**走。整张压暗 0.35× 之后它从
    0.011579 掉到 0.001417，比一张真糊的图（0.005476）还低——只看绝对值就会把一张
    曝光保守的好照片标成「糊」。除以灰度方差后压暗那张回到 0.2969，与真图的 0.2996
    基本同一格，而真糊仍然掉到 0.1444。这两个数一起用，才既是「模糊检测」又不是
    「暗=糊」。（数值全部出自 packaging/pick-calibrate.py。）

    第三个数是护栏：画面本身平坦（graystd→0）时比值不可信——纯色平坦给 0.0，
    平坦加噪声给 20.0，两头都荒唐。低于 `CONTRAST_FLOOR` 时调用方必须报「判据不适用」。
    """
    g = to_gray_measured(rgb)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return {"lapvar": 0.0, "ratio": 0.0, "contrast": 0.0}
    lap = (g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1]
           - 4.0 * g[1:-1, 1:-1])
    lv = float(np.var(lap) / (255.0 * 255.0))
    gv = float(np.var(g) / (255.0 * 255.0))
    return {"lapvar": lv,
            "ratio": (lv / (gv + 1e-9) if gv > 0.0 else 0.0),
            "contrast": float(np.sqrt(gv))}


def sharpness(rgb: np.ndarray) -> float:
    """归一化拉普拉斯方差（`clarity` 的第一格，标定台与旧读数沿用这个名字）。"""
    return clarity(rgb)["lapvar"]


def exposure_shares(rgb: np.ndarray) -> tuple[float, float]:
    """(欠曝占比, 过曝占比)：luma 落在纯黑/纯白裁切档的像素比例。"""
    g = to_gray_measured(rgb)
    n = float(g.size)
    under = float((g <= DARK_CUTOFF).sum()) / n
    over = float((g >= BRIGHT_CUTOFF).sum()) / n
    return under, over


# ---------------------------------------------------------------- 眼睑几何
def eye_openness(landmarks, *, image_size) -> float | None:
    """两只眼取小的「睁开比」= 上下睑中点像素距离 / 内外眼角像素距离。

    **必须按像素算，不能拿归一化坐标直接开 hypot**：FaceMesh 的 x 除以宽、y 除以高，
    两个方向的分母不同。横着量眼裂宽、竖着量睑间距，直接用归一化值就是把 y 的距离
    当成 x 的距离——同一张脸在 1024×1280 上读 0.370、在 1570×950 上读 0.754，差整整
    一个 H/W（标定台上实测）。这不是小数位问题，是量纲问题。

    用同一只眼自己的宽做分母，所以它与脸在画面里多大、离镜头多远、在哪一格都无关；
    两只眼取小值是因为「被头发挡住一只」会把均值拉高，而我们要问的是「有没有一只明显
    没开」。点数不够 478 契约时返 None 而不是猜：拿模板点阵去量眼睑是一种伪装。
    """
    lm = np.asarray(landmarks, dtype=np.float32)
    w, h = int(image_size[0]), int(image_size[1])
    if lm.ndim != 2 or lm.shape[0] < 478 or lm.shape[1] < 2 or w <= 0 or h <= 0:
        return None
    px = lm[:, :2] * np.array([w, h], dtype=np.float32)     # 归一化 → 像素
    out = []
    for eye in (EYE_LEFT, EYE_RIGHT):
        width = float(np.hypot(*(px[eye["inner"]] - px[eye["outer"]])))
        if width <= 1e-6:
            return None
        gap = float(np.hypot(*(px[eye["lower"]] - px[eye["upper"]])))
        out.append(gap / width)
    return float(min(out)) if out else None


# ---------------------------------------------------------------- 结论合成
def group_duplicates(items: list[tuple[str, int]], max_bits: int) -> list[list[str]]:
    """按汉明距离聚成近似组（并查集，距离 ≤ max_bits 就连边）。

    组是「像」的关系闭包，不是等价类：A像B、B像C 时 A 与 C 可能不像——这一点必须
    写在 notes 里，因为用户会拿它当「这三张重复」的结论读。
    """
    idx = {p: i for i, (p, _h) in enumerate(items)}
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if hamming(items[i][1], items[j][1]) <= max_bits:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups: dict[int, list[str]] = {}
    for p, i in idx.items():
        groups.setdefault(find(i), []).append(p)
    return [v for v in groups.values() if len(v) > 1]


def blur_read(m: Measures, blur: str, batch_median: float | None) -> dict | None:
    """清晰度这一格的全部判据合成，返回 reason（不成立则 None）。

    三种说法必须分开，因为它们是三种事实：
    · `blur`：绝对能量与相对比值**都**低（跨图可比的「明显糊」）；
    · `soft_vs_batch`：只比同批中位数软一大截（连拍里挑那张虚的，正是这个场景）；
    · 对比度不足时不判（返回 kind=`flat`，写在 notes 里而不是当成「清晰」）。
    """
    if m.contrast < CONTRAST_FLOOR:
        return {"kind": "flat", "method": "normalized-laplacian-variance",
                "value": round(m.sharpness, 6), "threshold": CONTRAST_FLOOR,
                "text": f"画面自身对比度 {m.contrast:.5f} 低于下限 {CONTRAST_FLOOR}"
                        "（纯色/平坦时清晰度判据不适用）：这一格不写「清晰」，也不写「糊」"}
    lo_abs = BLUR_SENSITIVITY[blur]
    lo_ratio = BLUR_RATIO_SENSITIVITY[blur]
    if m.sharpness < lo_abs and m.ratio < lo_ratio:
        return {"kind": "blur", "method": "clarity-lapvar-ratio",
                "value": round(m.sharpness, 6), "threshold": lo_abs,
                "ratio": round(m.ratio, 4), "ratio_threshold": lo_ratio,
                "text": f"高频能量 {m.sharpness:.6f} < {lo_abs} 且相对自身对比度 "
                        f"{m.ratio:.4f} < {lo_ratio}（两个条件都要满足：只看绝对值会把"
                        "整体压暗的好照片报成糊图，实测压暗 0.35× 的绝对值是 0.001417）"}
    med = float(batch_median or 0.0)
    factor = BLUR_REL_FACTOR[blur]
    if med > 0.0 and m.ratio < med * factor:
        return {"kind": "soft_vs_batch", "method": "clarity-ratio-vs-batch-median",
                "value": round(m.ratio, 4), "threshold": round(med * factor, 4),
                "batch_median": round(med, 4),
                "text": f"相对清晰度 {m.ratio:.4f} 只有同批中位数 {med:.4f} 的 "
                        f"{(m.ratio / med * 100.0):.0f}%（档系数 {factor}）——"
                        "同批里它明显更软；绝对能量没到线，所以这只建议复核"}
    return None


def suggest(m: Measures, *, group: list[str], is_leader: bool, rank_in_group: int,
            dup_bits: int | None, dup: str = "standard", blur: str = "standard",
            exposure: str = "standard", eyes: str = "standard",
            batch_median_ratio: float | None = None, group_scope: dict | None = None,
            user_marked: bool = False, group_eye_rule=None) -> dict:
    """把读数折成「建议 + 原因」。每一条原因都带着**数值与阈值**，可复核。

    `user_marked` 是「这一格已经有用户自己的标签/标记/回收站」：那时建议只作为旁注报出，
    `overridable` 恒为真，且 `labels` 不参与任何删除动作（这一层根本没有删除能力）。
    """
    reasons: list[dict] = []
    labels: list[str] = []
    if len(group) > 1:
        labels.append("similar")
        # 分组看的是**会话里已经量过的全部哈希**，不是只看在跑的这几张：只重跑一张就把
        # 它的组缩成一组，等于"动一下滑块，徽章上的组数自己变了"。范围也报出去，用户
        # 看得见这个组是从多少张里数出来的（手册：相似分组不是绝对重复判定）
        scope = dict(group_scope or {})
        extra = ""
        if scope.get("pooled") and scope.get("analyzed") and scope["pooled"] > scope["analyzed"]:
            extra = (f"（本次新量 {scope['analyzed']} 张，另 {scope['pooled'] - scope['analyzed']} "
                     f"张沿用上次量过的哈希参与分组）")
        reasons.append({"kind": "similar_group", "method": "dhash64-hamming",
                       "value": int(dup_bits or 0), "threshold": int(DUPLICATE_SENSITIVITY[dup]),
                       "group_size": len(group), "rank": int(rank_in_group), "scope": scope,
                       "text": (f"与组内 {len(group) - 1} 张近似（汉明距离 {dup_bits} 位，"
                                f"档上限 {DUPLICATE_SENSITIVITY[dup]}）{extra}；"
                                + ("按代理读数排序在前，仅供人工对照，不代表原片或人物表现最佳" if is_leader
                                   else "按代理读数排序在后，不代表较差；请复核原片再决定"))})
    br = blur_read(m, blur, batch_median_ratio)
    if br is not None:
        if br["kind"] != "flat":
            labels.append("blur" if br["kind"] == "blur" else "soft")
        br["text"] = "仅为长边160代理图的细节读数，不判定原片失焦/运动模糊：" + br["text"]
        reasons.append(br)
    if m.under > EXPOSURE_SENSITIVITY[exposure]:
        labels.append("underexposed")
        reasons.append({"kind": "underexposed", "method": "luma-clipping",
                        "value": round(m.under, 5), "threshold": EXPOSURE_SENSITIVITY[exposure],
                        "text": f"luma≤{DARK_CUTOFF} 的像素占 {m.under * 100:.1f}%"
                                f"（档上限 {EXPOSURE_SENSITIVITY[exposure] * 100:.0f}%）；"
                                "仅量代理亮度近黑占比，不证明原始传感器裁切或欠曝"})
    if m.over > EXPOSURE_SENSITIVITY[exposure]:
        labels.append("overexposed")
        reasons.append({"kind": "overexposed", "method": "luma-clipping",
                        "value": round(m.over, 5), "threshold": EXPOSURE_SENSITIVITY[exposure],
                        "text": f"luma≥{BRIGHT_CUTOFF} 的像素占 {m.over * 100:.1f}%"
                                f"（档上限 {EXPOSURE_SENSITIVITY[exposure] * 100:.0f}%）；"
                                "仅量代理亮度近白占比，不证明原始传感器裁切或过曝"})
    eye_labels, eye_reasons, rule_state = eye_hints(m, eyes, group_eye_rule)
    labels.extend(eye_labels)
    reasons.extend(eye_reasons)
    return {"schema": SCHEMA, "path": m.path, "labels": labels,
            "suggest": ("review" if labels else "none"),
            "overridden_by_user": bool(user_marked),
            "overridable": True, "auto_deleted": False, "auto_trashed": False,
            "sensitivities": {"duplicate": dup, "blur": blur,
                              "exposure": exposure, "eyes": eyes},
            "group_eye_rule": GE.settings(group_eye_rule), "group_eye_rule_state": rule_state,
            "reasons": reasons, "measures": m.for_json(),
            "notes": ["像素度量是确定性旁注；眼睑位置依赖FaceMesh模型，不是闭眼分类器或身份识别",
                      "只测解码代理及长边160缩图，非原片100%焦点/传感器曝光验收；无标签不代表质量合格",
                      "哈希现为固定9×8共64位；旧版阈值未对新版真实照片重新标定，距离仅供人工复核",
                      "近似组是「像」的关系闭包，不是绝对重复判定（A像B、B像C 不保证 A像C）",
                      "阈值出处：packaging/pick-calibrate.py 在同一夹具上的实测读数；"
                      "夹具是程序化的脸，只能定方向，不能当真人阈值",
                      "建议不改动、不删除、也不移动任何源文件；人工标签/标记/回收站优先"]}


def eye_hints(m: Measures, eyes: str, group_eye_rule=None):
    """Only Rust decides the optional group predicate. Unknown never passes."""
    rule = GE.settings(group_eye_rule)
    state = GE.decision(m, rule)
    labels, reasons = [], []
    if m.eye_open is None or not np.isfinite(m.eye_open):
        state = 'unknown' if rule['more_than'] is not None else 'disabled'
        reasons.append({'kind': 'eyes_unknown', 'method': 'facemesh-eye-aperture',
                        'value': None, 'threshold': EYE_SENSITIVITY[eyes],
                        'text': m.eye_note or '没有可用眼睑几何；未知，不代表睁眼或通过'})
    elif state == 'omit':
        reasons.append({'kind': 'eyes_omitted_by_rule', 'method': 'detected-group-eye-rule-v1',
                        'value': m.face_detection['count'], 'threshold': rule['more_than'],
                        'text': f"按用户规则省略闭眼提示：本次实际检测到 {m.face_detection['count']} 张脸，"
                                f"严格多于 {rule['more_than']}。检测上限32；不是完整人数统计，"
                                '不是睁眼、分析通过或质量合格；仍请人工复核'})
    elif m.eye_open < EYE_SENSITIVITY[eyes]:
        labels.append('eyes_closed')
        reasons.append({'kind': 'eyes_closed', 'method': 'facemesh-eye-aperture',
                        'value': round(m.eye_open, 5), 'threshold': EYE_SENSITIVITY[eyes],
                        'text': f'眼裂睁开比 {m.eye_open:.3f} 低于档阈值 {EYE_SENSITIVITY[eyes]:.3f}'
                                '（上下睑距离/眼裂宽，不是闭眼分类器；仅供复核）'})
    if state in ('unknown', 'unavailable') and rule['more_than'] is not None:
        reasons.append({'kind': 'eyes_rule_unknown', 'method': 'detected-group-eye-rule-v1',
                        'value': None, 'threshold': rule['more_than'],
                        'text': '例外未生效：检测证据缺失/过期或Rust规则不可用；未省略已有闭眼提示，'
                                '未知不代表睁眼或通过。需要时显式重新测量'})
    return labels, reasons, state


def reapply_eye_rule(suggestion, path, rule):
    """Recompute only eye hints from fenced cache; never invoke FaceMesh/decoder."""
    if not reusable(suggestion, path, suggestion.get('edge'),
                    suggestion.get('sensitivities'), suggestion.get('model_dir')):
        raise ValueError('原片、模型或缓存版本已变化；旧提示失效，请显式重新测量')
    m = restore_measures(path, suggestion['measures'])
    labels, reasons, state = eye_hints(m, suggestion['sensitivities']['eyes'], rule)
    result = dict(suggestion)
    result['labels'] = [v for v in suggestion['labels'] if v != 'eyes_closed'] + labels
    result['reasons'] = [r for r in suggestion['reasons'] if not r['kind'].startswith('eyes_')] + reasons
    result['suggest'] = 'review' if result['labels'] else 'none'
    result['group_eye_rule'] = GE.settings(rule)
    result['group_eye_rule_state'] = state
    return result


def visible(suggestion, path, error=None):
    """Session display never presents a known stale exemption as a current hint."""
    if not suggestion:
        return None, error
    try:
        m = restore_measures(path, suggestion['measures'])
        if (suggestion.get('fingerprint') != fingerprint() or source_stamp(path) != m.source_stamp
                or (m.face_detection and GE.current(m, hash_model=False) is None)
                or (suggestion.get('group_eye_rule_state') == 'omit' and not m.face_detection)):
            raise ValueError('stale')
    except (KeyError, TypeError, ValueError, OSError):
        return None, '原片、检测模型或缓存版本变化；旧提示已隐藏，未知不代表通过，请重新测量'
    return suggestion, error


def thresholds_for_json() -> dict:
    """把这几份档位原样报出去（ready 事件与 UI 的「按哪条线判的」共用这一个出处）。"""
    return {"duplicate": dict(DUPLICATE_SENSITIVITY), "blur_energy": dict(BLUR_SENSITIVITY),
            "blur_ratio": dict(BLUR_RATIO_SENSITIVITY), "blur_relative": dict(BLUR_REL_FACTOR),
            "exposure": dict(EXPOSURE_SENSITIVITY), "eyes": dict(EYE_SENSITIVITY),
            "contrast_floor": CONTRAST_FLOOR,
            "luma_cutoffs": [DARK_CUTOFF, BRIGHT_CUTOFF]}


def fingerprint() -> str:
    """这一份判据的指纹：阈值与算法名一改，指纹就变，事件里能看出是哪一版量出来的。"""
    blob = repr((SCHEMA, ALGO_VERSION, MEASURE_EDGE, sorted(DUPLICATE_SENSITIVITY.items()),
                 sorted(BLUR_SENSITIVITY.items()), sorted(BLUR_RATIO_SENSITIVITY.items()),
                 sorted(BLUR_REL_FACTOR.items()), CONTRAST_FLOOR,
                 sorted(EXPOSURE_SENSITIVITY.items()),
                 sorted(EYE_SENSITIVITY.items()), GE.VERSION, GE.EVIDENCE_SCHEMA, DARK_CUTOFF, BRIGHT_CUTOFF)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
