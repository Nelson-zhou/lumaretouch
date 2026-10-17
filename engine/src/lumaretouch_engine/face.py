"""导入期单次预计算：人脸关键点 + 语义掩膜。

两步走（总工 2026-10-16 定），这个文件是两个后端共同服务的那条通路：
* **通路**（本轮）：数据结构契约、显存挂载、IPC 事件、换图/换设备的生命周期。
* **精度**（下轮）：真实正脸 + MediaPipe 478 点物理贴合度验收。

MediaPipe 是**可选运行时插件**（决策 B）：不进 deb 依赖、不进 CI 主门禁，许可审计与装法
记在 `engine/requirements-mediapipe.txt`。通路回归永久由 synthetic 承担，这样“没装插件”
与“插件坏了”在两条臂上长得不一样。

两条硬规矩，都是前面几个里程碑用真金白银换来的：

1. **不许静默降级。** 请求 `mediapipe` 后端而依赖或模型不在，直接 `MissingBackend` 报错，
   绝不偷偷换成 synthetic 然后报一个"预计算成功"。上一轮「会话在 CPU 上跑却标 cuda」
   就是这么变成一份自洽废数据的。
2. **synthetic 后端的名字里就写着它不是人脸模型。** 它给的是占位几何 + 一条经典色度
   皮肤规则，用来验契约/生命周期/显存挂载，**不能**当检测精度证据用。用例只断言形状、
   值域、常驻与恒等性，不断言"这是脸"。
"""

from __future__ import annotations

import importlib.util
import os
import time
from dataclasses import dataclass, field

import numpy as np

# MediaPipe Face Landmarker 的输出点数；契约里钉死，M1-3c 的网格形变按这个索引布局
NUM_LANDMARKS = 478

BACKENDS = ("synthetic", "template", "mediapipe")

# 模型权重不入库（计划决策 9），首启由安装器按 sha256 拉官方源；引擎只读不吃下载
MODEL_DIR_ENV = "LRT_MODEL_DIR"
DEFAULT_MODEL_DIR = os.path.expanduser("~/.cache/lumaretouch/models")
FACE_LANDMARKER_MODEL = "face_landmarker.task"
SELFIE_SEGMENTER_MODEL = "selfie_segmenter.tflite"


class MissingBackend(RuntimeError):
    """请求的后端不可用。调用方必须把它当错误处理，不许退到别的路径继续跑。"""


# --------------------------------------------------------------------- 产物契约
@dataclass
class FacePrecompute:
    """一次预计算的产物，全部在 CPU 侧 numpy；上 GPU 由 vram.PreviewPipeline 负责。"""

    landmarks: np.ndarray                  # (478,3) float32，x/y 归一化到代理帧 [0,1]，z 相对深度
    masks: dict[str, np.ndarray]           # 通道名 -> (H,W) float32 [0,1]
    backend: str
    t_detect_ms: float
    t_masks_ms: float
    face_box: tuple[float, float, float, float] | None = None     # 归一化 (x0, y0, x1, y1)
    notes: list[str] = field(default_factory=list)

    def stack(self) -> tuple[np.ndarray, list[str]]:
        """按名字排序堆成 (K,H,W)，通道名顺序因此是确定的、与 dict 插入顺序无关。"""
        names = sorted(self.masks)
        if not names:
            raise ValueError("掩膜为空：契约要求至少一个通道")
        arr = np.stack([self.masks[n] for n in names], axis=0).astype(np.float32)
        return np.ascontiguousarray(arr), names

    def meta(self, h: int, w: int) -> dict:
        arr, names = self.stack()
        return {
            "backend": self.backend,
            "num_landmarks": int(self.landmarks.shape[0]),
            "landmark_shape": list(self.landmarks.shape),
            "mask_channels": names,
            "mask_shape": [int(arr.shape[0]), int(arr.shape[1]), int(arr.shape[2])],
            "mask_bytes_f32": int(arr.nbytes),
            "detect_ms": round(self.t_detect_ms, 2),
            "masks_ms": round(self.t_masks_ms, 2),
            "face_box": list(self.face_box) if self.face_box else None,
            # 几何看上去像不像一张脸（判据只写在 geometry_warning 里）：UI 拿布尔值
            # 开提示，不去 parse 上面那条 notes 的中文。
            "geometry_warning": geometry_warning(self.face_box),
            "proxy": [h, w],
            "notes": self.notes,
        }


def _now_ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


# --------------------------------------------------------- 经典色度皮肤先验（规则）
def skin_mask_np(rgb: np.ndarray) -> np.ndarray:
    """YCbCr 色度范围的经典皮肤规则，输出 (H,W) float32 [0,1]。

    这不是神经网络，也不需要权重：Cr∈[133,173]、Cb∈[77,127] 是肤色在 YCbCr 里的
    传统取值范围。用它做两件事：给 synthetic 后端一个真实随图变化的掩膜，以及给
    占位关键点提供一个"贴在亮肤色区域上"的位置。它当然分不清皮肤与同色衣物，
    所以精度回归阶段必须换成真分割模型，不许拿这条规则下结论。
    """
    from .ops.guided import _box_np          # 同一套积分图盒式滤波，不另写一份

    x = rgb.astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    # BT.601 → YCbCr（JPEG 那一套系数，与 Pillow 的 convert("YCbCr") 同源）
    cb = 128.0 + (-0.168736 * r - 0.331264 * g + 0.5 * b) * 255.0
    cr = 128.0 + (0.5 * r - 0.418688 * g - 0.081312 * b) * 255.0
    in_range = ((cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173)).astype(np.float32)
    # 软化边界 + 去掉单像素麻点：积分图两次，成本与半径无关
    soft = _box_np(in_range[None, None], 6)[0, 0] * 4.0
    return np.clip(soft, 0.0, 1.0)


# ------------------------------------------------------------------------- 后端
class SyntheticFace:
    """占位后端：真实皮肤掩膜（规则）+ 网格化占位关键点。只用于通路回归。"""

    name = "synthetic"
    requires_models = False

    def __init__(self):
        self.notes = ["synthetic 后端：关键点为占位几何，不是人脸模型输出；掩膜为经典色度规则"]

    def __call__(self, rgb: np.ndarray) -> FacePrecompute:
        h, w = rgb.shape[:2]
        t0 = time.perf_counter()
        mask = skin_mask_np(rgb)
        box = _tight_box(mask)
        lm = _grid_landmarks(box, h, w)
        t_detect = _now_ms(t0)
        return FacePrecompute(
            landmarks=lm,
            masks={"skin": mask},
            backend=self.name,
            t_detect_ms=t_detect,
            t_masks_ms=0.0,           # 掩膜与"检测"在同一个规则里出，拆开报会像在测两种东西
            face_box=box,
            notes=list(self.notes),
        )


class TemplateFace:
    """脸形模板后端：把一张解析正脸拟合到肤色包围盒上。零依赖、零权重、零许可负担。

    与 synthetic 的差别只有一条，但正是 M2-b 需要的那一条：它给的 478 点**按 MediaPipe
    拓扑布局**，点号→部位是对的，所以“左脸轮廓”“下巴尖”“虹膜中心”能按部位取到位置。
    与 mediapipe 的差别也只有一条：位置是按肤色盒摆的，不是按眼睛鼻子实际在哪找的。

    因此它能承担两件、且只承担两件：
      1. 让五官微调在没装 mediapipe 插件的机器上也能端到端跑通（产品不能因为一个
         带许可门禁的可选依赖而整个功能不可用）；
      2. 给形变的**通路/生命周期/每帧成本**提供真几何证据。
    它**不能**当精度证据：模板贴合度另由 mediapipe 后端负责（m1-3b-acc 仍阻在许可门禁）。
    这一点写进 notes，而且 deform_done 事件会把 backend 原样上报，UI 得能显示。
    """

    name = "template"
    requires_models = False

    def __init__(self):
        self.notes = ["template 后端：478 点为脸形模板按肤色盒拟合，部位语义正确、"
                      "贴合度不验收（精度回归需 mediapipe 插件）"]

    def __call__(self, rgb: np.ndarray) -> FacePrecompute:
        from .ops.deform import analytic_frontal_landmarks

        h, w = rgb.shape[:2]
        t0 = time.perf_counter()
        mask = skin_mask_np(rgb)
        box = _tight_box(mask)
        lm = _fit_template(analytic_frontal_landmarks(), box)
        t_detect = _now_ms(t0)
        notes = list(self.notes)
        # 几何可信度提示：肤色包围盒撑到整幅时，这张图上的“皮肤”一定不止脸。
        # 2026-10-17 的真人照片（红发 + 脖子胸口 + 画面左下角一只手）就是这么
        # 把模板撑到 [0,0,1,1] 的：五官微调按这套点搬，slim_face=0.9 改动了 98.6%
        # 的画幅，其中 57.6% 落在人工标注的脸盒之外。那一次量出来之后，这句话就得
        # 跟着几何一起走，不能只写在文档里。两条线：贴边≥3 条且覆盖 >60%
        # （非紧凑的一团皮肤），或干脆贴满四边且覆盖 >85%（包围盒就是整幅）。
        # 普通大头照不会同时越这两条。
        bw, bh = box[2] - box[0], box[3] - box[1]
        share = max(0.0, bw) * max(0.0, bh)
        edges = sum([box[0] <= 1e-6, box[1] <= 1e-6, box[2] >= 1 - 1e-6, box[3] >= 1 - 1e-6])
        if geometry_warning(box):
            notes.append(
                f"肤色包围盒覆盖画面 {share:.0%} 并贴到 {edges} 条边：这张图上的皮肤区域"
                "多半不止脸（脖子/胸口/手/暖色头发都算在内），模板落点可能不在脸上，"
                "五官微调会作用到大片非脸区域。要按脸落点，请装 mediapipe 插件后端")
        return FacePrecompute(
            landmarks=lm,
            masks={"skin": mask},
            backend=self.name,
            t_detect_ms=t_detect,
            t_masks_ms=0.0,        # 与 synthetic 同一条理由：掩膜与“检测”出自同一个规则
            face_box=box,
            notes=notes,
        )


def _fit_template(lm: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """把模板关键点的自带外接盒等比仿射到目标盒里（保宽高比、居中、不越界）。

    各向异性拉伸会把脸拉成方脸，而且“左右脸对称内收”在拉伸后不再对称。所以取
    均匀缩放因子 min(bw/tw, bh/th)：宁可上下留白，也不把模板拽长。
    """
    x0, y0, x1, y1 = box
    tx0, ty0 = float(lm[:, 0].min()), float(lm[:, 1].min())
    tw = max(float(lm[:, 0].max()) - tx0, 1e-6)
    th = max(float(lm[:, 1].max()) - ty0, 1e-6)
    bw, bh = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    s = min(bw / tw, bh / th)
    out = lm.copy()
    out[:, 0] = x0 + (bw - tw * s) * 0.5 + (lm[:, 0] - tx0) * s
    out[:, 1] = y0 + (bh - th * s) * 0.5 + (lm[:, 1] - ty0) * s
    return np.ascontiguousarray(np.clip(out, 0.0, 1.0), dtype=np.float32)


class MediaPipeFace:
    """真实后端：MediaPipe Face Landmarker（478 点）+ Selfie Segmenter（person 掩膜）。

    依赖 `mediapipe` 与两个官方模型文件。任何一个缺失都抛 MissingBackend 并说清缺什么，
    因为"装了但没跑起来"和"没装"在报表上必须长得一样明显——悄悄换后端是本节最贵的错误。
    """

    name = "mediapipe"
    requires_models = True

    def __init__(self, model_dir: str | None = None):
        if importlib.util.find_spec("mediapipe") is None:
            raise MissingBackend(
                "mediapipe 未安装。按已定的 B 方案它是一个**可选运行时插件**，不进 deb 也不进 CI 主"
                "门禁；依赖树（会把 opencv-contrib-python 与 matplotlib 一并拉进来）与逐包许可审计全部写在"
                " engine/requirements-mediapipe.txt，不许绕过那份审计直接 pip install。")
        from .decode import load_rgb      # noqa: F401  （仅为语义清晰：本类只吃代理帧）

        self.model_dir = model_dir or os.environ.get(MODEL_DIR_ENV) or DEFAULT_MODEL_DIR
        missing = [m for m in (FACE_LANDMARKER_MODEL, SELFIE_SEGMENTER_MODEL)
                   if not os.path.isfile(os.path.join(self.model_dir, m))]
        if missing:
            raise MissingBackend(
                f"模型文件缺失：{missing}（应在 {self.model_dir}）。权重不入库，"
                "需由安装器按 sha256 从官方源拉取后再跑精度回归。")
        # 真正建图推迟到首次调用：构造一次 MediaPipe 图就要初始化其 native 运行时，
        # 放在这里会让「只查询后端可用性」也付出几百毫秒
        self._graphs = None

    def _ensure(self):
        if self._graphs is None:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            lm_path = os.path.join(self.model_dir, FACE_LANDMARKER_MODEL)
            sg_path = os.path.join(self.model_dir, SELFIE_SEGMENTER_MODEL)
            landmarker = mp_vision.FaceLandmarker.create_from_options(
                mp_vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=lm_path),
                    num_face_landmarks=1,
                    output_face_blendshapes=False,
                    output_facial_transformation_matrixes=False))
            segmenter = mp_vision.Segmenter.create_from_options(
                mp_vision.SegmenterOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=sg_path),
                    output_category_mask=False))
            self._graphs = (landmarker, segmenter)
        return self._graphs

    def __call__(self, rgb: np.ndarray) -> FacePrecompute:
        import mediapipe as mp

        landmarker, segmenter = self._ensure()
        view = np.ascontiguousarray(rgb)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=view)
        h, w = rgb.shape[:2]

        t0 = time.perf_counter()
        res = landmarker.detect(img)
        if not res.face_landmarks:
            raise RuntimeError("MediaPipe 未在这张图上检测到人脸（代理档分辨率过低或构图不符）；"
                               "不许退成占位点数——那会让 478 点契约看起来通过了")
        pts = np.array([[p.x, p.y, p.z] for p in res.face_landmarks[0]], dtype=np.float32)
        if pts.shape != (NUM_LANDMARKS, 3):
            raise RuntimeError(f"关键点数量不是 {NUM_LANDMARKS}：得到 {pts.shape}，契约破坏")
        t_detect = _now_ms(t0)

        t1 = time.perf_counter()
        seg = segmenter.detect(img)
        if not seg.mask:
            raise RuntimeError("MediaPipe 分割没返回掩膜")
        mask = np.asarray(seg.mask[0].numpy_view, dtype=np.float32)
        if mask.shape != (h, w):
            mask = _resize_float(mask, h, w)
        t_masks = _now_ms(t1)

        return FacePrecompute(
            landmarks=pts,
            masks={"skin": mask},          # 自检分割给的是"人"，通道名先按现有语义命名，M2 换多类模型再拆
            backend=self.name,
            t_detect_ms=t_detect,
            t_masks_ms=t_masks,
            face_box=_norm_box(pts),
            notes=["mediapipe 后端：478 点为真实检测输出"],
        )


def build(backend: str, model_dir: str | None = None):
    """按名字构造后端。`auto` = 有 mediapipe 且模型齐就用真的，否则用 synthetic 并说明原因。

    auto 不回落 template：那会把“没装插件”与“装了插件但检不出脸”两种情况在报表上
    混成一个结果。template 必须显式点名，这样事件里的 backend 字段就是“有人主动选
    了模板拟合”的硬证据。
    """
    if backend == "mediapipe":
        return MediaPipeFace(model_dir)
    if backend == "synthetic":
        return SyntheticFace()
    if backend == "template":
        return TemplateFace()
    if backend == "auto":
        try:
            return MediaPipeFace(model_dir)
        except MissingBackend as e:
            s = SyntheticFace()
            s.notes.append(f"auto 回落 synthetic：{e}")
            return s
    raise ValueError(f"未知预计算后端: {backend}（可用：{', '.join(BACKENDS)}, auto）")


# --------------------------------------------------------------------- 小工具
def geometry_warning(box) -> bool:
    """这套几何看上去不像一张脸（而不是“意见”）：命令层与事件层共用同一个判据。

    UI 要拿它开提示，就不能去 parse notes 里的中文句子（那是双出处：改一个字
    界面就静悄悄不再警告）。规则只在这里写一份，文字提示只是它的展开。
    """
    if not box:
        return False
    x0, y0, x1, y1 = (float(v) for v in box)
    share = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    edges = sum([x0 <= 1e-6, y0 <= 1e-6, x1 >= 1 - 1e-6, y1 >= 1 - 1e-6])
    return (edges >= 3 and share > 0.60) or (edges >= 4 and share > 0.85)


def _tight_box(mask: np.ndarray) -> tuple[float, float, float, float]:
    """掩膜质心包围盒（归一化）。取 ≥0.5 的强皮肤区，退化时用整图中心一块兜底。"""
    h, w = mask.shape
    ys, xs = np.nonzero(mask >= 0.5)
    if xs.size < max(16, 0.002 * h * w):
        return (0.2, 0.15, 0.8, 0.85)
    x0, x1 = xs.min() / w, (xs.max() + 1) / w
    y0, y1 = ys.min() / h, (ys.max() + 1) / h
    return (float(x0), float(y0), float(x1), float(y1))


def _grid_landmarks(box: tuple[float, float, float, float], h: int, w: int) -> np.ndarray:
    """在皮肤包围盒上铺一张 NUM_LANDMARKS 的点阵——**占位**，不是人脸拓扑。

    为什么要它：M1-3b/M1-3c 的通路要验的是「478×3 的张量能算出来、能进显存、
    能随图变、能随设备迁移」，这些都不需要真拓扑。真贴合度由 mediapipe 后端负责。
    坐标用行列索引生成，所以对同一输入逐字节确定（不依赖 RNG 或哈希序）。
    """
    n = NUM_LANDMARKS
    cols = 22
    rows = (n + cols - 1) // cols                      # 22 列 × 22 行 = 484，取前 478
    x0, y0, x1, y1 = box
    idx = np.arange(n, dtype=np.float32)
    gx = (idx % cols) / (cols - 1)
    gy = np.floor_divide(idx, cols) / max(rows - 1, 1)
    z = np.zeros_like(gx)
    lm = np.stack([x0 + gx * (x1 - x0), y0 + gy * (y1 - y0), z], axis=1).astype(np.float32)
    assert lm.shape == (NUM_LANDMARKS, 3) and (0.0 <= lm[:, :2]).all() and (lm[:, :2] <= 1.0).all()
    return np.ascontiguousarray(lm)


def _norm_box(pts: np.ndarray) -> tuple[float, float, float, float]:
    return (float(pts[:, 0].min()), float(pts[:, 1].min()),
            float(pts[:, 0].max()), float(pts[:, 1].max()))


def _resize_float(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """最近邻缩到代理帧尺寸：不引新依赖，也不给掩膜造出中间灰阶。"""
    ys = (np.arange(h) * a.shape[0] / h).astype(np.int64)
    xs = (np.arange(w) * a.shape[1] / w).astype(np.int64)
    return np.ascontiguousarray(a[ys[:, None], xs[None, :]].astype(np.float32))
