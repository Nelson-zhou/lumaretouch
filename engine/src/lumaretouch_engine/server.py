"""引擎主进程：stdin 收 JSON lines 命令，stdout 发 JSON lines 事件。

像素不进这条通道——它走 /dev/shm 双缓冲，这里只发「第 seq 帧已就绪、
在 slot N、t_emit_ns=...」这种几十字节的通知。
"""

from __future__ import annotations
from . import primary_calibration_state as PCS, primary_calibration_adapters as PCA
from . import colour_grading_state as CGS, colour_grading_adapters as CGA
from . import photo_grain_state as PGS, photo_grain_adapters as PGA
from . import photo_grain_runtime as PGR
from . import selective_colour_state as SCSL, selective_colour_adapters as SCLA
from . import colour_editor_state as CES, colour_editor_adapters as CEA, colour_editor_runtime as CER
from . import extended_tone_state as ETS, extended_tone_host as ETH
from . import photo_detail_state as PDS, photo_detail_host as PDH
from . import fringe_repair_state as FRS, fringe_repair_native as FRN
from .fringe_repair_host import FringeRepairHostMixin
from . import fringe_repair_render as FRR
from . import canvas_guides_host as CGH

import argparse
import copy
from pathlib import Path
import json
import math
import os
import queue
import sys
import threading
import time

# The native host launches this module directly. Apply the boundary before any
# image/model dependencies load; the console entry uses bootstrap for the same reason.
if __name__ == "__main__":
    if os.environ.get("LRT_PARENT_PID"):
        from .inspection_worker import bind_parent
        bind_parent(int(os.environ["LRT_PARENT_PID"]))
    from .privacy import require_offline_or_exit
    require_offline_or_exit()

from .privacy import policy_status
from .frames import test_frame
from .shm import FrameShm, monotonic_ns, shm_name
# 磨皮参数的默认值只在这里取一次：vram 在模块层就容忍 torch 缺失（CPU job 也能 import），
# 在这里复用它们而不是写第二份字面量，否则默认值与生产值会漂移。
from .vram import DEFAULT_BROAD_GAIN, DEFAULT_DETAIL_GAIN, DEFAULT_EPS, DEFAULT_MID_GAIN, \
    DEFAULT_RADIUS, DEFAULT_TEXTURE_RADIUS, DEFAULT_REPAIR, GRADE_SCOPES, LightOp, RepairOp, \
    warm_device
from .ops.light import DB_EXPOSURE_LIMIT, DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS
from .ops.deform import KINDS, KIND_LIMIT, DeformGeometryError, check_amounts
from .ops import curves as CURVES
from .ops import levels as LEVELS
from .levels_controller import LevelsController, LevelsPorts
from .ops.lut import LutError, check_amount, load_cube_file, parse_cube
from . import fabric_controller as FABRIC
from .ops import enhance as ENH
from . import facial_wrinkle_state as WSTATE
from . import blush_makeup_project as BLUSHLIB, lipstick_project as LIPSTICKLIB, eyeliner_project as EYELINERLIB, eyelash_project as EYELASHLIB, brow_makeup_project as BROWMAKEUPLIB
from . import lip_makeup_state as LIPS, lip_makeup_runtime as LIPR, brow_shape_state as BROWS, brow_shape_runtime as BROWR, nose_shape_state as NOSES, eye_shape_state as EYES, eye_shape_runtime as EYER, mouth_shape_state as MOUTHS, mouth_shape_runtime as MOUTHR, nose_shape_runtime as NOSER
from .ops.grade import DH_LIMIT, DS_LIMIT, DV_LIMIT, GradeError, check_params
from .ops.hsl import (BAND_CENTERS, BAND_NAMES, HUE_LIMIT as HSL_HUE_LIMIT,
                      LUM_LIMIT as HSL_LUM_LIMIT, SAT_LIMIT as HSL_SAT_LIMIT)
from .ops.presets import PRESETS, PresetError, get_preset, preset_grade, preset_lut
from .ops.upscale import SCALES
from .ops import birefnet
from .ops import upscale as U
# M5 底片条：扫描与缩略图的全部口径都在 session 层，命令层只发事件与管线程。
from . import raw as R
# 项目持久化：编解码与落盘全在 project 层（纯函数 + 文件 IO，不依赖 torch），
# 命令层只负责“校验互斥 → 调它 → 把事实发成事件”。
from . import project as PJ
from . import tasks as T
# 模块作用域与预设（LNX-P0-PRESET / lnx.batch.v1.module_scope）：参数合不合法只有
# 一个出处（scope），落盘边界只有一个出处（preset_store）。命令层只做“守卫 → 调它们
# → 把事实发成事件”，不在这里再摸一份“哪些参数属于哪个模块”——预设与批量必须同一语义，
# 分开抄就会出“预设里没有的参数被批量偷偷同步了”。
from . import local_mask_state as LM
from . import effect_recovery_state as ERS, effect_recovery_runtime as ERR
from . import manual_liquify_state as MLS, manual_liquify_runtime as MLR
from . import local_grade_layers as LG, local_grade_runtime as LGR, local_grade_source as LGS
from . import studio_background_state as SBS, studio_background_runtime as SBR
from . import id_background_state as IDS, id_background_runtime as IDR
from . import creative_document_host as CDH
from .studio_tools_dispatch import StudioToolsMixin
from .preview_lifecycle import PreviewLifecycleMixin
from .portrait_geometry_dispatch import PortraitGeometryMixin
from .master16_policy import Master16PolicyMixin
from .body_pose_host import BodyPoseHostMixin
from .hair_colour_controller import HairColourHostMixin, MUTATIONS as HAIR_MUTATIONS
from .people_host import PeopleHostMixin
from .workflow_ports import WorkflowPortsMixin
from . import library_query_host as LQ
from .library_query_metadata import capture_decoded as library_capture_decoded, capture_file_identity as library_file_identity
from .sample_library_host import SampleLibraryHostMixin
from .preset_organisation_host import PresetOrganisationHostMixin
from . import source_relocation_host as SRH
from . import managed_import_host as MIH
from .semantic_colour_host import SemanticColourHostMixin
from . import semantic_colour_state as SCS, semantic_colour_runtime as SCR
from .command_reader import read_commands
from . import optics_state as OPS, optics_runtime as OPR
from . import sky_replacement_state as SKS, sky_replacement_runtime as SKR
from . import scope as SC
from . import preset_controller as PRS
from . import hsl_recipe as HSL_RECIPE
from . import white_balance_recipe as WB
from . import reference_color_state as RCS, reference_color_runtime as RCR
from . import preset_store as PS
from .project import ProjectError
from . import session as S
# 挑图建议（LNX-PICK-001）：度量与档位全部在 picks 层（纯 numpy，不依赖 torch/mediapipe），
# 命令层只负责「校验 → 起线程 → 把事实发成事件」。眼睑那一格要用 FaceMesh，它是可选的：
# 后端不在就每一格如实报 eyes_unknown，绝不退成「睁眼」（不许静默降级）。
from . import picks as PK
# M4 导出：FORMATS/尺寸边界与落盘器全部从 export 走，命令层不掌一份格式名单（双出处）。
from .export import (DEFAULT_TILE, FORMATS, MAX_TILE, MIN_TILE, SHARPEN_AMOUNT_LIMIT,
                     UPSCALE_NOT_WIRED,
                     ExportSpec,
                     export_image, resample_field, write_file)
from . import __version__
from . import history_policy
from . import history_controller as HC
from . import batch_sync as BS
from .inspection_controller import InspectionController
from .repair_record import validate_repair_ops

PROTOCOL_VERSION = 1


def runtime_report() -> dict:
    """ready 里那份运行时账单（M5-c 发布校验用）。只报事实，不做判断。

    只用 importlib.metadata 读 dist-info，**不 import torch**：import torch 要好几秒，
    把它塞进握手等于给每次启动加几秒；而发布校验要问的是“这个解释器里装了哪套包、
    版本对不对”，元数据就够用——真跑不跑得起由 set_device 那条路说。
    """
    from importlib import metadata
    out = {"python": ".".join(map(str, sys.version_info[:3]))}
    for pkg in ("numpy", "pillow", "tifffile", "imagecodecs", "torch", "torchvision"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None      # 没装就写 None：发布校验拿它判“运行时不完整”，不许静默省略键
    return out


# 磨皮强度的出厂默认。写一次：`__init__`、新文档的起始状态、load_image 的可选参数
# 三处都要它，抄三份字面量就是下一轮改默认值时漏改的那一处。
DEFAULT_STRENGTH = 0.0

# 本进程的“写手形状”只算一次：包元数据不会在一个进程里变，而 `_project_state()` 挂在
# `session_state` 上（每次导入、每次标签都要读一次）。拿 importlib.metadata 重扫三遍
# 不值得，而更重要的是：这个值必须在一个会话内是同一个，否则“环境一致”这句话
# 会随扫描顺序飘。
_WRITER: dict | None = None


def _current_writer() -> dict:
    global _WRITER
    if _WRITER is None:
        _WRITER = PJ.writer_stamp()
    return _WRITER

# 跑靶模式：
#   copy               纯拷贝，M0 通路基线
#   pipeline / pipeline_copyin  逐帧 numpy 往返（M1-2 对照组）
#   pipeline_resident  源图与输出帧常驻显存（M1-2 目标组）
#   image_stream       真图常驻流（M1-3a）：需先 load_image，每帧只拖滑块系数
MODES = ("copy", "pipeline", "pipeline_copyin", "pipeline_resident", "image_stream")
# torch 首次建 ROCm 上下文 + 显存池要几百毫秒，混进均值里会把稳态算胖，先空跑几帧
WARMUP_FRAMES = 8


def _clamp_strength(v) -> float:
    """强度只接受 [0,1]。load_image 与 set_strength 必须同一规：一边夹一边不夹的话，
    越界值会被包框里的 clamp_ 削平成一张看不出错但语义错的帧，而 image_ready.strength
    照原值上报。"""
    value = float(v)
    if not math.isfinite(value):
        raise ValueError("strength 必须是有限数")
    return min(max(value, 0.0), 1.0)


def emit(obj: dict) -> None:
    """stdout 会被主循环与跑靶线程同时写，必须串行化。"""
    from .project_recovery_runtime import observe
    observe(obj)
    from .custom_lut_scope import public_view
    obj = public_view(obj)
    with _EMIT_LOCK:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()


_EMIT_LOCK = threading.Lock()


class _TaskControl:
    """stdin 线程写、worker 线程读的三个位。

    用 Event 而不是布尔量：worker 在边界上等继续时要能睡着，不能空转把 CPU 吃了。
    它们**不是状态**：“能不能暂停/是否已暂停”的答案在 tasks.py 的转移表里，这里只有
    “有人提过这个请求”。把请求位当状态就是 TASK-006 拒绝的那种写法（按下就算已暂停）。
    """

    def __init__(self):
        self.pause = threading.Event()
        self.resume = threading.Event()
        self.cancel = threading.Event()


class Engine(FringeRepairHostMixin, PresetOrganisationHostMixin, HairColourHostMixin, Master16PolicyMixin, BodyPoseHostMixin, PeopleHostMixin, PreviewLifecycleMixin, StudioToolsMixin, PortraitGeometryMixin, WorkflowPortsMixin, SampleLibraryHostMixin, SemanticColourHostMixin):
    def __init__(self, session: str):
        self.session = session
        self.shm: FrameShm | None = None
        self.bench: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.device = "cpu"
        self._cuda = False        # 真的是 GPU 才需要 synchronize，CPU 上调一次是白调
        self._torch = None        # set_device 时握一次模块引用，免得每帧走一遍 import
        self._quit = False
        self._inspection_snapshot_tx = None
        self._inspection_snapshot_result = None
        self._inspection_snapshot_id = None
        self._inspection_snapshot_last_id = 0
        self._inspection_snapshot_state = "idle"
        self._inspection_snapshot_request = None
        self._inspection_job = None
        self._inspection_render_config = None
        self._inspection_snapshot_error = None
        self._pipe_out = None
        self._vram = None
        # 常驻会话对应的那张源图（CPU 侧 numpy），留着是为了换设备时能就地重建。
        # F 轮第一轮就是栽在这里：load_image 先于 set_device，会话建在 cpu 上，
        # 之后切 cuda 也只改了 self.device，旧张量静静躺在 CPU 上跑了 91 ms/帧，
        # 而 bench_done 照样报 cuda:true——数据看起来完全正常，结论全是假的。
        self._src_rgb = None
        # 真图会话是否建立。不能拿 self._vram is not None 当“已导图”：跑靶的合成会话
        # 会把它顶掉，之后 set_strength 就不报错而是拿彩条图冒充用户照片。
        self._image_loaded = False
        self._load_id = ""
        # 预计算产物的 CPU 原件留着：换设备重建会话时要就地重挂，不能“迁移完就没脸了”。
        # 掩膜与关键点只在当前会话的当前尺寸上成立，这是本节的主要不变式。
        self._precompute = None
        self._precompute_backend = None
        self._channel = None
        # 多人图里“正在改哪一张”的选择（PORTRAIT-003）。它必须在这里有个起点：
        # `_capture_state` 是从 live 字段抄的，而一张从未预计算过的图也会走快照（切文档/
        # 存工程），不在这里初始化就会在那些路径上撞 AttributeError。上一版就是只进了
        # 名单与快照、没进构造，响在 test_history 那三条臂上。
        self._face_index = 0
        self._face_box = None
        self._face_explicit = False
        # 人脸名单的**人工账**（PORTRAIT-006 人工纠正优先）：`disabled` 是用户关掉的
        # 那一只（误检），`added` 是用户框出来补上的那一张（漏检）。两条都存**归一化
        # 脸盒**而不是 index：重检测/换后端之后 index 会重新排，而盒还能认出是同一个人
        # （与 `_face_box` 存盒同一条理由）。
        # 它进 DOC_FIELDS（切文档带上、存工程带上、撤销能退），而**不进 PROXY_BOUND**：
        # 归一化坐标与代理档无关，换一档代理它仍指同一个人。`_face_box` 进那边是因为
        # 它是"那一次分析里第几张"的凭证，而这份账是"用户对哪一个人做过什么"的判断。
        self._face_manual = {"disabled": [], "added": []}
        # 磨皮参数（M1-3c）：与 strength 不同，它们变了滤波结果才会变。缓存键靠这个字典，
        # 所以它必须存在引擎侧而不是只在调用方：否则报表上看不出「这一帧重算了没」。
        self._params = dict(radius=DEFAULT_RADIUS, eps=DEFAULT_EPS,
                            texture_radius=DEFAULT_TEXTURE_RADIUS,
                            broad_gain=DEFAULT_BROAD_GAIN, mid_gain=DEFAULT_MID_GAIN,
                            detail_gain=DEFAULT_DETAIL_GAIN)
        # 消除笔（M1-4）的操作列表在引擎侧也有份：常驻会话会因换设备而重建，
        # 只存在 pipe 里的话迁完就“脸还在但修补全没了”。存的是输入（画笔 uint8），不是结果。
        # redo 栈也得有一份：不然切一次设备就把“重做”历史静默抹掉，与“撤销/重做都靠重放”矛盾。
        self._repair_ops: list = []
        self._redo_ops: list = []
        self._op_seq = 0
        # 修容层（M2-a2）在引擎侧也有一份：它跟消除笔一样是“只存输入”的图层，
        # 换设备重建会话时要能就地重放。参数（强度/带限半径）也存在引擎侧，
        # 因为新会话的默认值不等于当前会话的值。
        self._light_ops: list = []
        self._light_redo: list = []
        self._light = dict(exposure=DEFAULT_DB_EXPOSURE, radius=DEFAULT_DB_RADIUS)
        # 形变层（M2-b）：存的是每一格的滑块值（键集 = KINDS），单位场不存（它能从关键点重算，
        # 而关键点已经在 _precompute 里）。换设备重建时重新 build 一次，55 ms。
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        # 「层在而单位场不在」这一格（CORE-001 重开 / 会话迁移）：关键点不随工程文件走
        # （它是模型派生物），所以重开那一刻必然出现「用户明明有一层瘦脸，而单位场还没解出来」。
        # 上一版没有这一格：_attach_pipeline 见没关键点就把整层归零，于是「保存重开后配方少了
        # 一层」——而配方完整恢复正是 CORE-001 的 then。这一格是待重挂标记：滑块值留在
        # _deform["amounts"]，built=False，关键点一回来就由 _rebuild_deform_for_landmarks 补上。
        self._deform_defer = False
        # 层级合成（LNX-PORTRAIT-004）：**全人物默认**这一份与**逐张脸的覆盖**那一份。
        # `_deform["amounts"]` 存的是"当前在改那一张的最终生效值"（合成结果），它才是
        # 会话真在渲染的那组数；默认与覆盖各自独立存着，改哪一层都只动那一层。
        # 覆盖按**脸盒**认人而不是按 index：与 _face_box 同一条理由（检测顺序不可预期，
        # 拿旧序号对新名单就是一次静默选型，会把 A 的覆盖盖到 B 脸上）。
        # 诚实边界（写进 ADR）：一层形变服务一张脸——单位场只从一张脸的轮廓解控制点，
        # 所以同一时刻只有"被选中那一张"按它的有效值生效；换人就是换那份几何
        # （test_acceptance_p1 第 ⑥ 段逐字节钉着这件事）。不许把这句写成"多人同时各改各的"。
        self._deform_default = {k: 0.0 for k in KINDS}
        self._deform_overrides: list = []   # [{"box": [x0,y0,x1,y1], "amounts": {kind: v}}]
        # 调色层（M3-a2）：引擎侧存的是那张表本身（CPU 原件）与混合系数。
        # 表不存会话里只存在这里是不够的：常驻体积张量活在一块设备上，换设备必须重挂。
        self._lut = None
        self._lut_amount = 1.0
        # 定向层（M3-b）：引擎侧只存四个数（它不持有张量）。与调色层同一条规矩：
        # 随图清、随设备迁移重提交。
        self._grade = (0.0, 0.0, 0.0, 1.0)
        # COLOR-004 局部调色：作用域（all/skin/brush）与画笔区域（代理坐标 uint8 覆盖度）。
        # 它们与 _grade 一样是图层状态、不是渲染缓存，所以生命周期也必须一样（快照、
        # 切文档、换设备、随代理档作废）。区域与作用域**成对作废**：brush 没有区域、
        # skin 没有掩膜都是到 apply_grade 取权重那一刻才抛，也就是每一帧都抛——那正是
        # 「命令收下而画面不动」的形状，所以作废必须一起作，不留半截。
        self._grade_scope = "all"
        self._grade_mask = None
        self._creative_document = None; self._creative_asset_records = {}; self._creative_base = None
        self._local_masks = LM.empty(); self._local_grade_layers = LG.empty()
        self._effect_recovery = ERS.empty(); self._manual_liquify = MLS.empty(); self._studio_background = SBS.empty(); self._id_background = IDS.empty(); self._id_background_bundle = None; self._optics = OPS.empty(); self._sky_replacement = SKS.empty(); self._blush_makeup_library = BLUSHLIB.empty(); self._lipstick_library = LIPSTICKLIB.empty(); self._eyeliner_library = EYELINERLIB.empty(); self._eyelash_library = EYELASHLIB.empty(); self._brow_makeup_library = BROWMAKEUPLIB.empty(); self._lip_makeup = LIPS.neutral(); self._brow_shape = BROWS.neutral(); self._brow_shape_owner = None; self._nose_shape = NOSES.neutral(); self._nose_shape_owner = None; self._eye_shape = EYES.neutral(); self._eye_shape_owner = None; self._mouth_shape = MOUTHS.neutral(); self._mouth_shape_owner = None; self._reference_color = RCS.empty(); self._reference_color_bundle = None; self._semantic_init(); self._body_init()
        # PORTRAIT-009 眼牙增强：三个子功能的值 + 会话里有没有那份场 + **它属于哪一张脸**。
        # `box` 这一格不是装饰：这一层的掩膜是从**那一张**的 478 点画出来的。换人选时若
        # 不认脸盒，就会把 A 的美白静默涂到 B 身上——那是 SCOPE-001 拦的同一件事，
        # 而画面确实"有人在动"，看不出来。
        # `_enhance_defer` 是 CORE-001 那一课的直接产物：关键点不随工程文件走，重开那一刻
        # 必然出现"用户有一层美白而场还没画出来"，没有这一格就会像上一版那样整层归零。
        self._enhance = dict(amounts={k: 0.0 for k in ENH.AMOUNT_KEYS}, built=False, box=None)
        self._fabric_amount = 0.0
        self._enhance_defer = False
        # P0 全局曝光/白平衡：会话侧同样只存那三个数（加一个参考白）。它必须与
        # _grade 走完全一样的生命周期：初始化、换设备重挂、快照、状态上报——漏一个
        # 就是“宿主以为还写着 0.5 EV，引擎里其实是 0”那种两边错配。
        self._crop_rect = (0.0, 0.0, 1.0, 1.0)   # P0 lnx.crop.v1（中性=全画幅）
        self._crop_rotation = 0.0
        self._extended_tone = ETS.default()
        self._photo_detail = PDS.default()
        self._fringe_repair = FRS.neutral()
        self._photo_grain = PGS.neutral()
        self._photo_grain_source_renderer = lambda **kw: self._write_current_frame(kw["reason"])
        self._colour_grading = CGS.neutral()
        self._selective_colour = SCSL.neutral()
        self._colour_editor = CES.neutral()
        self._primary_calibration = PCS.neutral()
        self._exposure = (0.0,) * 7
        self._exposure_ref_k = None
        self._wb_options = WB.default_options()
        # 八色 HSL（原创扩展）：24 个数 = 8 段 × (色相/饱和度/明亮度)。与曝光层
        # 同一条生命周期（初始化、重挂、快照、上报），否则又是“切张图滑块还在、
        # 画面已经回中性”。
        self._hsl = (0.0,) * 24
        self._curves = CURVES.default_curves()
        self._levels = LEVELS.default_levels()
        # 换底层（M6）：存“可重建一份常驻遮罩所需的一切”——遮罩原件（代理坐标
        # uint8）、背景色、后端与参数。随图清、随代理档作废、随设备重挂（与掩膜同命）。
        self._bg = dict(active=False, matte=None, bg=None, backend=None,
                        tol=None, softness=None)
        # 当前生效的内置预设名（走 path/text 或手动改定向时为 None）。它不是装饰：
        # 它决定“调色强度”要不要连带施加到定向层，也是 UI 显示“预设/手动”的唯一出处。
        self._lut_preset = None
        # 分段计时的自洽计数：子段之和超过整帧内核段的帧数（只可能是重复计时）。
        # kernel 靠减法得出并夹到 0，不记这一笔就永远看不出某段被计了两次。
        self._seg_over_frames = 0
        self._wlock = threading.Lock()   # 跑靶线程与 stdin 线程都在写同一块双缓冲
        self._strength = _clamp_strength(DEFAULT_STRENGTH)
        # 当前文档的源路径：导出默认导的就是这一张，而导入时只留下了像素没留下名字。
        self._doc_path: str | None = None
        self._export: threading.Thread | None = None
        self._export_args: tuple | None = None
        # M5-a 底片条：会话的文档列表与“哪一份是当前文档”。每张图自己一套编辑状态，
        # 切换是“存回去 / 取出来”而不是“清空重来”——后者是 Lightroom 式的丢工。
        self._docs: list = []
        self._doc_index = -1
        # 代理预算是**会话级**的，不是逐格的：底片条里每张图都得解在同一档预览尺度上，
        # 不然从一张 400×504 切到一张 672×848 会把 shm 拆了重建——宿主那边正 mmap 着旧
        # inode 读帧，拿到的是上一张图的旧数据（不报错，只是错）。逐图预算只当记账信息留着。
        self._proxy_budget: int | None = None
        # 缩略图在独立线程里解：底片条一百张不能把主循环（以及它负责的帧通路）顶住。
        self._thumbs: threading.Thread | None = None
        # RAW 秒开那一帧的账（decode.py 的分界规则：它只填首屏，不进会话）
        self._preview_info: dict | None = None
        self._thumb_stop = threading.Event()
        self._thumb_args: tuple | None = None
        # 挑图建议（LNX-PICK-001）：与缩略图同一个形状——独立线程、逐张发事件、写回前按
        # path 再认一次格子。它是**派生旁注**：不进工程文件（见 `_project_build`）、不进撤销栈
        # （不在 EDIT_CMDS 里）、不改源文件（这一路只有读）。
        self._picks: threading.Thread | None = None
        self._pick_stop = threading.Event()
        self._pick_args: tuple | None = None
        # 底片条那一列表会被两个线程碰：stdin 线程换整张表，缩略图线程改单格的
        # thumb/thumb_error。GIL 保不了“读→比对→写”这三步，所以自己上锁。
        self._doclock = threading.Lock()
        # 全局历史（M5-b）：栈里存的是"这一步执行前"的文档状态快照，不是指令。
        # 挂在 live 上、随文档格走：切底片条时与状态一起存回/装回，每个文档各有一条自己的历史。
        self._undo: list = []
        self._redo: list = []
        self._hist_group = ""           # 最近一步的手势身份（同组在窗口期内合并）
        self._hist_group_ns = 0
        # 项目（LNX-P0-PROJECT / CORE-001）：内存里那一份工程文档、它落盘的路径、
        # 以及“存过之后又改过没有”。脏标记只有一个推送点：`_history_record` 判出
        # “这一条命令真的改了文档状态”那一刻。拿“底片条内容与保存时不同”当脏会报两件
        # 假事：重新解码的调色表对象身份变了（签名就是按身份比的），以及缩略图线程
        # 晚到一步改了单格。两者都会让“未保存”徽章在刚保存完就亮起来。
        self._project: dict | None = None
        self._project_source_notice: dict = {}
        self._project_path: str | None = None
        self._project_path_prev: str | None = None
        self._project_dirty = False
        self._project_saved_ns: int | None = None
        self._project_disk_sha256: str | None = None
        # 批量任务台账（LNX-P0-TASK）：状态与审计轨迹在 tasks 层，这里是运行时的三个位。
        self._tasks: dict = {}            # task_id → 记录（插入序就是队列序）
        self._task_args: dict = {}        # task_id → 当时那份导出参数（含 numpy 图层，只活在会话）
        self._task_seq = 0
        self._task_ctl: "_TaskControl | None" = None
        self._export_task: dict | None = None
        # 批量同步台账（LNX-P0-BATCH / BATCH-004）：batch_id → 每一格的 commit 前快照
        # 与 commit 后的那组模块参数。撤销时要拿“我当初写了什么”去比“现在还是不是它”，
        # 不然就分不清“这格没被动过”与“用户动过又被我抹掉”。
        self._batches: dict = {}
        self._batch_seq = 0
        # 上一笔同步的事实（commit/undo），随 session_state 的 `sync.last_result` 报出去：
        # UI 那句“同步了几张、跳过几张为什么”只能从这里来。
        self._sync_last: dict | None = None
        # 当前文档上“最后一次套用的预设”（id/名/作用域/套完那一组参数）。UI 的下拉
        # 显示它而不是前端自己记一份：报之前还要比一次参数（见 `_preset_last_applied`）。
        self._preset_last: dict | None = None
        # 名单铁律的第三条腿：DOC_FIELDS 里每一项都必须在构造里有个起点。前两条腿
        # （_fresh_doc_state 与 _capture_state 互相校名单）照不出“构造里少写一行”：那两份
        # 名单是同一个口径写在了两处，而 AttributeError 要走到 _capture_state 才响——本轮真实撞到
        # （face 那三键进了名单与快照，却没进 __init__）。这里构造末尾自校一次，
        # 把“少一行”提前成创建引擎就响。
        _missing = [k for k in self.DOC_FIELDS if not hasattr(self, k)]
        assert not _missing, f"__init__ 没给这些文档字段起点：{_missing}"

    # ------------------------------------------------------------ 通路自检
    def cmd_hello(self, _p: dict):
        from .skin_colour_state import capability as skin_colour_capability
        from .skin_finish_state import capability as skin_finish_capability
        from .skin_gloss_state import capability as skin_gloss_capability
        from .skin_texture_state import capability as skin_texture_capability
        from .face_contour_state import capability as face_contour_capability
        from .face_size_state import capability as face_size_capability
        from .lower_face_state import capability as lower_face_capability
        from .mid_face_state import capability as mid_face_capability
        from .chin_shape_state import capability as chin_shape_capability
        from .chin_length_state import capability as chin_length_capability
        from .philtrum_state import capability as philtrum_capability
        from .eye_symmetry_state import capability as eye_symmetry_capability
        from .brow_enhance_state import capability as brow_enhance_capability
        from .body_skin_evenness_state import capability as body_skin_evenness_capability
        from .skin_evenness_state import capability as skin_evenness_capability
        from .lip_texture_state import capability as lip_texture_capability
        emit({"event": "ready", "protocol": PROTOCOL_VERSION, "command_ack": 1, "inspection_protocol": 1, "color_capture_protocol": 1, "color_scopes_protocol": 1, "batch_preflight_protocol": 1, "preset_result_protocol": 1, "xmp_import_protocol": 1, "preset_organisation_protocol": 1, "source_relocation_protocol": 1, "managed_import_protocol": 1, "project_recovery_protocol": 1, "white_balance_result_protocol": 1, "color_picker_capture_protocol": 1, "color_picker_result_protocol": 1, "white_balance_capture_protocol": 1, "source_patch_capture_protocol": 1, "source_patch_result_protocol": 1, "clone_stamp_protocol": 1, "heal_vector_protocol": 1, "local_masks_result_protocol": 1, "effect_recovery_protocol": 1, "manual_liquify_protocol": 1, "manual_liquify_preview_protocol": 2, "optics_protocol": 1, "sky_replacement_protocol": 1, "sky_semantic_protocol": 1,"lip_makeup_protocol":1,"brow_shape_protocol":2,"nose_shape_protocol":2,"eye_shape_protocol":2,"mouth_shape_protocol":2,"people_protocol":1,"hair_colour_protocol":1,"eyeliner_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_eyeliner.so").is_file()),"iris_makeup_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_iris_makeup.so").is_file()),"eyelash_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_eyelash.so").is_file()),"brow_makeup_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_brow_makeup.so").is_file()),"lipstick_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_lipstick.so").is_file()),"blush_makeup_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_blush_makeup.so").is_file()),"eye_light_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_eye_light.so").is_file()),"reference_color_protocol":1,"sample_library_protocol":1,"semantic_colour_protocol":1,"primary_calibration_protocol":int(self._primary_calibration_service().available()),"colour_editor_protocol":int((Path(__file__).parent/"bin/liblrt_colour_editor.so").is_file()),"selective_colour_protocol":int((Path(__file__).parent/"bin/liblrt_selective_colour.so").is_file()),"photo_grain_protocol":int(PGR.available()),"colour_grading_protocol":int((Path(__file__).parent/"bin/liblrt_colour_grading.so").is_file()),"photo_detail_protocol":int(PDH.available()),"fringe_repair_protocol":int(FRN.available()),"extended_tone_protocol":int((Path(__file__).parent/"bin/liblrt_extended_tone.so").is_file()),"semantic_colour_workflow_protocol":1,"shoulder_shape_protocol":1,"leg_shape_protocol":1,"arm_shape_protocol":1,"waist_shape_protocol":1,"neck_shape_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_neck_shape.so").is_file()),"leg_length_protocol":int((Path(__file__).resolve().parent/"bin/liblrt_leg_length.so").is_file()), "studio_background_protocol": 1, "common_background_protocol": 1, "common_background_readback_protocol": 1, "id_background_protocol": 1, "local_grade_live_protocol": 1, "prompted_masks_protocol": 1, "curve_recipe_versions": [1, 2, 3], "pid": os.getpid(),
              # 版本自证（M5-c）：.deb 的 Version 取自 tauri.conf.json，这一份取自
              # packaging/VERSION 同步下来的 __version__。发布校验把两者对起来——分叉时
              # 装机 UI 上显示的版本与真正在跑的引擎版本就是两句话。
              # 协议号不动（加键属兼容扩展，宿主只读不判）。
              "version": __version__, **skin_colour_capability(), **skin_finish_capability(), **skin_gloss_capability(), **skin_texture_capability(), **face_contour_capability(),**face_size_capability(), **lower_face_capability(), **mid_face_capability(), **chin_shape_capability(), **chin_length_capability(), **philtrum_capability(), **eye_symmetry_capability(), **brow_enhance_capability(), **lip_texture_capability(), **skin_evenness_capability(), **body_skin_evenness_capability(),
              "runtime": runtime_report(),
              "privacy": policy_status(),
              # 内置预设清单（M3-b）：按钮上写什么字、按哪个名提交，全部由引擎说。
              # 前端抄一份名字就是双出处：资产改名后 UI 会静默拿着错名去撞拒绝。
              "presets": [{"name": k, "title": v.title} for k, v in sorted(PRESETS.items())],
              # 三个增量的硬边界也在这里报一次：滑块的行程在引擎说了为准之后才能开始渲染，
              # 不等一条 grade_done 才拿到范围（那时滑块已经错看了一轮）。
              "grade_limits": [DH_LIMIT, DS_LIMIT, DV_LIMIT],
              # M4：导出能力也由引擎说。前端抄一份格式名单或 tile 范围，就是下一轮改边界时
              # 漏改的那一处。
              "export_formats": sorted(set(FORMATS)),
              "export_tile": [MIN_TILE, MAX_TILE],
              "export_tile_default": DEFAULT_TILE,
              # 放大能力（M7）：倍率与后端名单同样由引擎说。前端刻一份"支持 2×/4×"或
              # "支持 AI 超分"，就是在无权重的机器上谎报能力。
              "upscale_scales": list(SCALES),
              "upscale_backends": U.scale_backends(),
              # 抠图后端清单（M6，与放大同一个口径）：birefnet 在权重未放行前不算可用。
              # 旧版只把这一句写在提交后的拒绝里，UI 的下拉项却无条件摆着——那是在
              # 邀请用户去撞一个注定空的请求。
              "matting_backends": birefnet.matting_backends(),
              # RAW 能力清单（M1 的 RAW 那一块）：基线只解公开规范 DNG 的未压缩/Deflate
              # 线性数据，厂商专有容器与 lossless JPEG 要 libraw 可选插件。前端拿这一
              # 份说话，而不是自己刻一个“支持 RAW”——那会把“解不开 CR2”写成已通过。
              "raw_backends": R.raw_backends(),
              # Native RGB16 writers, not Pillow RGB8 with a renamed bit-depth label.
              "export_bits": {"8": list(FORMATS), "16": ["tif", "tiff", "png"]},
              # M5-a 底片条：行程与上限同样由引擎说。前端自己刻一份“长边 160”或
              # “最多 512 张”，下一轮改上限时就是漏改的那一处（它会静默把图截小）。
              "session_actions": ["scan", "add", "select", "state", "thumbs", "stop_thumbs", "query"],
              # 形变（M2-b / PORTRAIT-004）的 action 与作用层名单同样由引擎说：命令层的
              # 拒绝文案里承诺了“名单在 ready 里”，这一格不写实就是假承诺。前端自己刻
              # 一份“set/clear”就是下一轮加 inherit 时漏改的那一处（它会撞未知 action）
              "deform_actions": list(self.DEFORM_ACTIONS),
              "deform_scopes": list(self.DEFORM_SCOPES),
              # 名单从引擎走：上一版前端自己抄了一份三元组，于是"引擎加了 kind 而
              # 屏幕上没有那一格控件"是可能发生的（而且 TS 编译期一句都不报）。
              "deform_kinds": list(KINDS),
              # 眼牙增强（PORTRAIT-009）的三个子功能名单与值域同样由引擎说：前端自己
              # 抄一份"眼白/虹膜/牙齿"就是下一轮加一格时漏改的那一处（而且 TS 一句不报）
              "enhance_subs": list(ENH.EFFECT_KEYS),
              "enhance_range": [0.0, float(ENH.AMOUNT_LIMIT)],
              "enhance_actions": list(self.ENHANCE_ACTIONS),
              # 人脸名单能收的动作（PORTRAIT-006）：前端自己刻一份就是下一轮加动作时
              # 漏改的那一处，而且 TS 一句都不报
              "face_actions": list(self.FACE_ACTIONS),
              "face_manual_iou": self.MANUAL_IOU_MIN,
              "deform_range": [-KIND_LIMIT, KIND_LIMIT],
              # 能收哪些后缀：只由 session.IMAGE_EXTS 定这一份，宿主拿它填原生
              # 选择框的过滤器。拷一份名单到 UI 里就是给自己埋雷：M9-c 把八个 RAW
              # 后缀收进来的那一次，UI 那份拷件不会跟着变，用户选不了、工程师说支持。
              "image_exts": sorted(S.IMAGE_EXTS),
              "thumb_edge": [S.MIN_EDGE, S.MAX_EDGE],
              "thumb_edge_default": S.EDGE,
              "thumb_max_bytes": S.THUMB_MAX_BYTES,
              "session_max_docs": S.MAX_DOCS,
              # M5-b 全局撤销/重做：行程、步数上限与手势合并窗口都由引擎说。
              # 前端刻一份"最多 64 步"或"700 ms 算一次手势"，下一轮改口径时漏改的就是它——
              # 而且这一次漏改不会报错，只会让按钮的灰与不灰和真实栈深对不上。
              "history_actions": list(self.HISTORY_ACTIONS),
              "history_max": self.HISTORY_MAX,
              "history_group_ms": self.HISTORY_GROUP_MS,
              "history_edit_cmds": list(self.EDIT_CMDS),
              "creative_document_protocol": 1,
              "canvas_guides_protocol": 1,
              "canvas_guides_actions": ["state", "set", "undo", "redo"],
              # 项目面的能力名单由引擎报出去（与 export 的格式名单同一条理由）：
              # 前端抄一份 action 名单，两边分叉时“不支持”与“拼错了”长得一模一样
              "project_actions": list(self.PROJECT_ACTIONS),
              "project_suffix": PJ.SUFFIX,
              "export_destination_protocol": 1, "task_actions": list(self.TASK_ACTIONS),
              # 挑图（LNX-PICK-001）：action 名单、四组档位的可选值、阈值本体与判据指纹
              # 全部由引擎说。前端刻一份「weak/standard/strong」或抄一个阈值数字，就是
              # 下一轮改判据时漏改的那一处——而它的表现是徽章悄悄改了含义。
              "pick_actions": list(self.PICK_ACTIONS),
              "pick_sensitivities": {k: sorted(v) for k, v in self.PICK_SENS_TABLE.items()},
              "pick_thresholds": PK.thresholds_for_json(),
              "pick_schema": PK.SCHEMA, "pick_algo": PK.ALGO_VERSION,
              "pick_fingerprint": PK.fingerprint(),
              "pick_edge": [self.PICK_MIN_EDGE, self.PICK_MAX_EDGE],
              "pick_edge_default": self.PICK_EDGE})

    # ------------------------------------------------------------ 帧缓冲
    def _ensure_shm(self, w: int, h: int) -> FrameShm:
        if self.shm and (self.shm.w, self.shm.h) == (w, h):
            return self.shm
        with self._wlock:
            if self.shm:
                self.shm.close()
                self.shm.unlink()
            self.shm = FrameShm(shm_name(self.session), w, h, slots=2, create=True)
        emit({"event": "shm_ready", "name": self.shm.name, "path": self.shm.path,
              "frame_identity_version": 1, "shm_instance": self.shm.instance_id.hex(),
              "w": w, "h": h, "slot_size": self.shm.slot_size,
              "pixel_size": self.shm.pixel_size, "total": self.shm.total})
        return self.shm

    # ------------------------------------------------------------ 跑靶
    def _reject_bench(self, msg: str, mode: str):
        """拒绝开跑：除了 error 还必须发 bench_done{failed}。

        只发 error 的话，宿主那边认为 bench 已经开起来了，前端会空轮询到超时（上一轮
        就是这么静默卡了 200 s），拿到的表现是“没数据”而不是“没跑成”。
        """
        emit({"event": "error", "error": msg})
        emit({"event": "bench_done", "frames": 0, "mode": mode, "failed": True,
              "device": self.device, "cuda": self._cuda, "reason": msg})

    def cmd_bench_start(self, p: dict):
        if "w" not in p or "h" not in p:
            # 少参数时原来是裸 int(p["w"]) 抛 KeyError，事件里只有一句 "KeyError: 'w'"，
            # 看不出是协议用错还是引擎坏了；说清缺什么、从哪拿（shm_ready 里的 w/h）
            self._reject_bench("bench_start 缺 w/h：应从 shm_ready 拿会话尺寸", p.get("mode", "copy"))
            return
        w, h = int(p["w"]), int(p["h"])
        if self._export is not None and self._export.is_alive():
            # 同一条理由与换图一样：跑靶与导出同抢一块卡，两边的帧成本账单都不是那个数
            self._reject_bench("导出进行中，拒绝开跑靶：等 export_done", p.get("mode", "copy"))
            return
        frames = int(p.get("frames", 600))
        interval_ms = float(p.get("interval_ms", 16.7))
        mode = p.get("mode", "copy")          # 见 MODES
        if mode not in MODES:
            # 不认得的模式不能默默当成 copy 跑：上一轮矩阵里写错模式名就会拿到
            # 一份“管线其实没跑”的数据，看上去还完全正常
            self._reject_bench(f"未知 bench 模式: {mode}（可用：{', '.join(MODES)}）", mode)
            return
        if mode == "image_stream":
            if not self._image_loaded:
                self._reject_bench("image_stream 需要先 load_image", mode)
                return
            if (int(p["w"]), int(p["h"])) != (self._vram.w, self._vram.h):
                # 尺寸不一致会在写 shm 时才爆，且报的是“字节数不对”，看不出根因；先拦住
                self._reject_bench(f"image_stream 尺寸 {p['w']}x{p['h']} "
                                   f"!= 已加载图的代理档 {self._vram.w}x{self._vram.h}", mode)
                return
        shm = self._ensure_shm(w, h)
        self.stop_flag.clear()
        self.bench = threading.Thread(target=self._bench_loop,
                                      args=(shm, frames, interval_ms, mode), daemon=True)
        self.bench.start()
        emit({"event": "bench_started", "frames": frames, "interval_ms": interval_ms,
              "mode": mode, "w": w, "h": h})

    def _sync(self) -> None:
        """GPU 内核是异步排队执行的：不在段边界 synchronize，内核时间会被记到
        后一段（D2H）的头上，分段就白分了。两条臂用同一套同步点，总量仍可比。"""
        if self._cuda:
            self._torch.cuda.synchronize()

    def _make_frame(self, shm: FrameShm, i: int, mode: str, pipe):
        """引擎侧一帧的全部工作，按模式分派。返回 (RGBA 帧, 各段 ms)。

        抽成一个方法是为了让 packaging/m1-vram-bench.py 能直接复用同一份代码——
        离线跑靶如果自己拼一份近似逻辑，量的数就不能代表产品通路。
        """
        seg = dict(synth=0.0, pre=0.0, filter=0.0, light=0.0, deform=0.0, lut=0.0,
                   grade=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0, readback=0.0)
        # image_stream 模拟拖滑块：系数在 0.25→0.75 上扫一个 100 帧周期，
        # 像素逐帧真的在变；常驻管线的系数跑靶如果只动 0.001，字节上几乎看不出区别
        if mode == "image_stream":
            strength = 0.25 + 0.5 * (i % 100) / 99.0
        else:
            strength = 0.6 + 0.001 * (i % 50)
        if pipe is not None:
            # 常驻路径：源图不重算、不上传，每帧只换一个系数
            channel = self._channel if mode == "image_stream" else None
            t = monotonic_ns()
            # 参数必须跟着走：不传的话调用方用 set_strength 改了半径，跑靶仍按默认值出帧，
            # 量的就不是产品通路（而且会多一次缓存重算混进数据里）
            out = pipe.retouch(strength, channel=channel, **self._params)
            self._sync()
            # M1-3c：kernel 段现在只是混合；重算滤波的那一笔单独列到 filter 段。
            # 两者不重叠（filter 由 prepare 自己量，kernel = 整段减去 filter），拼起来
            # 才是以前的“内核”，这样拖拽热路径的真实成本能被看见，也不会把合计算两遍。
            # 注意 pipeline_copyin 那条臂没有 filter 段：它调的是 retouch_t，滤波与混合
            # 在同一个表达式里拆不开（filter=0 不等于“它不滤波”）。跨臂对拍要比的是
            # copyin.kernel ≈ resident.filter + resident.kernel。
            whole = (monotonic_ns() - t) / 1e6
            seg["filter"] = float(getattr(pipe, "last_filter_ms", 0.0) or 0.0)
            # M2-a2：修容层也是热路径上可分离的一笔。它应当与 filter 同构：
            # 只在图层/参数变了的那一帧非 0，拖 strength 时恒为 0。不拆出来
            # 就会把 db 的开销记到 kernel 头上，而“拖滑块零重算”这条判据看不出来。
            seg["light"] = float(getattr(pipe, "last_light_ms", 0.0) or 0.0)
            # M2-b：形变与修容不同，它每帧真在跑（grid_sample），所以它不是“重算次数”
            # 而是“每帧成本”。零推理那条靠 deform_builds 不增来证，不靠这一段为 0。
            seg["deform"] = float(getattr(pipe, "last_deform_ms", 0.0) or 0.0)
            # M3-a2：调色与形变同构，也是每帧真在跑的一笔（grid_sample 3d）；它不是
            # “重算次数”而是“每帧成本”。不拆出来就会把它记到 kernel 头上，而
            # “挂上 LUT 后拖磨皮滑块仍零重算”那条判据就看不出是谁在花钱。
            seg["lut"] = float(getattr(pipe, "last_lut_ms", 0.0) or 0.0)
            # M3-b：肤色定向与调色同构（每帧真在跑的逐点内核，只是它不拿表而拿公式）。
            # 不拆出来，拖那三个滑块时花的 1.3 ms/帧就会全部记到 kernel 头上，而
            # “定向不作废磨皮缓存”与“定向每帧真跑了”两条判据都看不出是谁在花钱。
            seg["grade"] = float(getattr(pipe, "last_grade_ms", 0.0) or 0.0)
            # kernel 是“整段减去五个子段”，减法夹到 0 就看不出重复计时：子段之和超过整段
            # 只可能是某段被计了两次或计时嵌套了。当场记一笔，由 bench_done 说话——
            # 一个永远非负、越界也不报的数不是一个判据。
            seg_sum = seg["filter"] + seg["light"] + seg["deform"] + seg["lut"] + seg["grade"]
            if seg_sum - whole > 0.5:
                self._seg_over_frames += 1
            seg["kernel"] = max(whole - seg_sum, 0.0)
            t = monotonic_ns()
            pipe.pack(out)
            # 跑靶指纹（只给合成靶纸用）：常驻路径的源图不动，逐帧变化的像素只能靠盖序号块。
            # 真图流不能盖——那会在用户照片上刷一块彩色补丁；它的 strength 在扫，像素本来就在变。
            if mode == "pipeline_resident":
                pipe.stamp(i)
            self._sync()
            seg["post_gpu"] = (monotonic_ns() - t) / 1e6
            t = monotonic_ns()
            pixels = pipe.read_back()
            seg["readback"] = (monotonic_ns() - t) / 1e6
            return pixels, seg
        t = monotonic_ns()
        pixels = test_frame(shm.w, shm.h, i)
        seg["synth"] = (monotonic_ns() - t) / 1e6
        if mode in ("pipeline", "pipeline_copyin"):
            pixels, s = self._pipe_copyin(pixels, strength, **self._params)
            seg.update(s)
        return pixels, seg

    def _bench_loop(self, shm: FrameShm, frames: int, interval_ms: float, mode: str):
        """跑靶线程的入口：任何异常都必须变成一条事件。

        主循环的 try 包不到这个线程里。上一轮就是这个问题：`_open_vram` 里 torch
        报错或显存不够，线程静默死掉，调用方只能等超时，拿到一份「没跑但看上去正常」
        的数据。现在早退发 error + bench_done{failed}，脚本当场能看出来。
        """
        try:
            self._bench_run(shm, frames, interval_ms, mode)
        except Exception as e:
            emit({"event": "error", "error": f"bench 线程异常退出({mode}): {type(e).__name__}: {e}"})
            emit({"event": "bench_done", "frames": 0, "mode": mode, "failed": True,
                  "device": self.device, "cuda": self._cuda, "warmup": WARMUP_FRAMES})

    def _bench_run(self, shm: FrameShm, frames: int, interval_ms: float, mode: str):
        # 分段计时：测帧 / 上传 / 内核 / GPU 收尾 / 回读 / 写 shm / 发通知。
        # M0 必须知道 60fps 的天花板卡在哪一段——上一版只给一个总数，把合成图形的 17 ms
        # 当成了通路极限；M1-2 要证的是「内核没变快，快的全是搬运」，那就更得拆开。
        period = interval_ms / 1000.0
        acc = dict(synth=0.0, pre=0.0, filter=0.0, light=0.0, deform=0.0, lut=0.0,
                   grade=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0, readback=0.0,
                   shm=0.0, notify=0.0)
        # 重算次数：拖拽期零推理的直接证据。只要这个数不是 1（或 0），缓存就没真的生效，
        # 而按均值报 filter 会把它藏起来（600 帧里重算一次只有 0.0075 ms/帧）。
        refilters = 0
        # 修容层同一个口径：600 帧拖滑块期间 relight_frames 应当是 0，
        # 不为 0 就是 db 缓存没命中（键算错了），而均值会把它洗掉。
        relights = 0
        # M3-a2：调色是逐帧固定成本，没有“命中缓存”这一说。它只用来防“挂了一层却没跑”：
        # 表挂上且强度非 0 时它必须等于跑靶帧数，否则那一层只存在于上报里。
        lut_frames = 0
        # M3-b：定向也是逐帧固定成本（点火时）。与 lut 同一个用途：防“设了参数却没跑”。
        grade_frames = 0

        def snapshot(done: int) -> dict:
            return {k: round(v / max(done, 1), 3) for k, v in acc.items()}

        pipe = (self._vram if mode == "image_stream"
                else self._open_vram(shm.w, shm.h) if mode == "pipeline_resident" else None)
        # M2-b：拖 600 帧滑块期间一次 TPS 也不许解。deform_builds 只在 build_deform
        # 里递增，而 build_deform 只由 cmd_deform 触发——跑靶不碰它。取开头与结尾
        # 两个快照而不是只取结尾：只取结尾的话，“中途重解了三次但开头就是 3”看不出来。
        builds_at_start = int(getattr(pipe, "deform_builds", 0)) if pipe is not None else 0
        # 预热：跑完全相同的每帧工作（同一 _make_frame），但不写 shm、不发事件、不进统计
        for k in range(WARMUP_FRAMES):
            self._make_frame(shm, k, mode, pipe)
        self._sync()
        emit({"event": "bench_warmup", "frames": WARMUP_FRAMES, "mode": mode,
              "device": self.device, "cuda": self._cuda})

        next_t = monotonic_ns() / 1e9
        t_last_report = time.perf_counter()
        for i in range(frames):
            if self.stop_flag.is_set():
                break
            pixels, seg = self._make_frame(shm, i, mode, pipe)
            if seg.get("filter", 0.0) > 0:
                refilters += 1
            if seg.get("light", 0.0) > 0:
                relights += 1
            if seg.get("lut", 0.0) > 0:
                lut_frames += 1
            if seg.get("grade", 0.0) > 0:
                grade_frames += 1
            for k, v in seg.items():
                acc[k] += v
            t4 = monotonic_ns()
            with self._wlock:
                seq, t_emit, slot = shm.write_frame(pixels, presentation=self._frame_presentation() if mode=="image_stream" else self._frame_presentation("0", (shm.w,shm.h), "synthetic"))
            acc["shm"] += (monotonic_ns() - t4) / 1e6
            emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                  "w": shm.w, "h": shm.h, "mode": mode})
            acc["notify"] += (monotonic_ns() - t_emit) / 1e6
            next_t += period
            delay = next_t - monotonic_ns() / 1e9
            if delay > 0:
                time.sleep(delay)
            if time.perf_counter() - t_last_report > 2.0:
                emit({"event": "bench_progress", "done": i + 1, "total": frames,
                      **snapshot(i + 1)})
                t_last_report = time.perf_counter()
        emit({"event": "bench_done", "frames": frames, "mode": mode,
              "device": self.device, "cuda": self._cuda, "warmup": WARMUP_FRAMES,
              # pipe_device 才是真正跑了这 600 帧的设备。只报 self.device/cuda 的话，
              # 会话落在 CPU 上也能报出一份标着 cuda 的好数据。取局部 pipe 而不是
              # self._vram：后者会被别的命令顶掉，报的就不是刚才那一轮的服务者。
              "pipe_device": str(pipe.device) if pipe is not None else None,
              # 零推理跑靶的验收面：重算次数应当是 0（预热那 8 帧已经付掉一次性成本）
              "refilter_frames": refilters,
              "refilter_ms_total": round(acc["filter"], 2),
              "relight_frames": relights,
              "relight_ms_total": round(acc["light"], 2),
              "deform_ms_total": round(acc["deform"], 2),
              "deform_builds": (int(getattr(pipe, "deform_builds", 0)) - builds_at_start
                                if pipe is not None else 0),
              # M3-a2：调色是逐帧固定成本（不像 filter/light 有缓存命中），所以它没有
              # “重算次数”可证，只有“每帧真跑了多少帧”：挂上表且强度非 0 时它应当等于
              # frames，而 lut 均值为 0 就是“挂了一层却没跑”的当场证据。
              "lut_ms_total": round(acc["lut"], 2),
              "lut_frames": lut_frames,
              "grade_ms_total": round(acc["grade"], 2),
              "grade_frames": grade_frames,
              # 图层状态与每帧分段不能同名（上一版 `"light": dict(self._light)` 就是被
              # snapshot 里的同名字段吃掉的）。取局部 pipe 而不是 self._vram：后者会被
              # 别的命令顶掉，报的就不是刚才那 600 帧的服务者。
              "lut_state": dict(source=(pipe.lut.source if pipe is not None and pipe.lut else None),
                                size=(pipe.lut.size if pipe is not None and pipe.lut else 0),
                                amount=float(pipe.lut_amount) if pipe is not None else None,
                                lit=bool(pipe.has_lut()) if pipe is not None else False,
                                bytes_lut=pipe.lut_resident_bytes() if pipe is not None else 0),
              # M3-b：定向层状态与 lut_state 同构（不同名、不吃 snapshot 的同名键）。
              # dh/ds/dv/amount 取自局部 pipe：报的就是刚才那 600 帧真正在用的那组数。
              "grade_state": dict(dh=(pipe.grade_params[0] if pipe is not None else 0.0),
                                  ds=(pipe.grade_params[1] if pipe is not None else 0.0),
                                  dv=(pipe.grade_params[2] if pipe is not None else 0.0),
                                  amount=float(pipe.grade_amount) if pipe is not None else 1.0,
                                  lit=bool(pipe.has_grade()) if pipe is not None else False,
                                  bytes_grade=(pipe.grade_resident_bytes()
                                               if pipe is not None else 0)),
              # 分段不自洽的帧数：某段被重复计时时会在这里非 0，而不是表上看不出来
              "seg_over_frames": int(self._seg_over_frames),
              "params": dict(self._params),
              # 图层状态与每帧分段不能同名。上一版 `"light": dict(self._light)` 写在
              # `**snapshot()` 前面，而 snapshot 里就有同名的每帧 ms——字典字面量后写的
              # 覆盖先写的，于是上报里的 light 永远是那个毫秒数，曝光/半径根本送不出来，
              # 而且报表看起来完全自洽。M2-b 的 deform 撞上了同一条，一起改。
              "light_state": dict(self._light),
              "deform_state": dict(self._deform),
              **snapshot(frames)})

    # ------------------------------------------------------------ GPU 管线
    def _attach_pipeline(self, rgb, adopt: bool = True):
        """把一张 (H,W,3) uint8 接成 GPU 常驻会话。源图一次性进显存，之后不再回 CPU。

        adopt=False 给跑靶的合成会话用：它不能顶掉真图会话（self._vram/_src_rgb），
        否则一次 pipeline_resident 跑靶之后，“已导图”这个判定、set_strength 与
        bench_done.pipe_device 都会对着那张彩条图说话。"""
        from .vram import make_pipeline

        original_rgb = rgb
        if adopt and getattr(self, "_creative_base", None) is not None:
            from .creative_document_base import proxy_for_state
            rgb = proxy_for_state(rgb, {"_creative_base":self._creative_base}, max_pixels=self._proxy_budget, max_bytes=CDH.memory_budget())
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        pipe = make_pipeline(self.device, w, h, rgb)
        if pipe.fallback:
            emit({"event": "engine_warn", "warn": pipe.fallback})
        if adopt:
            self._vram = pipe
            pipe.teeth_colour_cancelled = lambda: bool(self._quit)
            pipe.photo_grain_source_output = lambda: CER.render_preview(self,pack=False) if CER.active(self) else PGR.render_preview(self,pack=False) if PGR.active(self) or self._fringe_active() else None
            pipe.colour_editor_source_input = lambda: CER.render_preview(self,pack=False,input_only=True)
            self._src_rgb = original_rgb
            from .creative_derived_repair_runtime import bind as bind_repair_source
            bind_repair_source(self)
            # 会话新建在另一个设备上：旧张量全在那边，这里按存下的画笔重放一遍。
            # 不重放就是“会话迁了、图层没迁”，与 M1-3a 那个“会话在 CPU 上跑却标 cuda”同形。
            if self._repair_ops or self._redo_ops:
                pipe.set_repair_ops(self._repair_ops, self._redo_ops)
            # 参数先于图层：新会话的 exposure 默认值不等于用户当前拖到的值，
            # 先挂图层再改参数会白跑一次 db（而且上报里的 exposure 与实际算的不是一个数）
            pipe.light_exposure = float(self._light["exposure"])
            pipe.light_radius = int(self._light["radius"])
            if self._light_ops:
                pipe.set_light_ops(self._light_ops, self._light_redo)
            # 形变层：单位场不存只重解（一次 55 ms，换设备本来就是重操作）。
            # 关键点不在（没 precompute）时不能默默建不起来：那会“迁了会话、
            # 滑块还在 0.6 但画面不动”，而事件里看不出异常。上一版这段只有 if、
            # 没有 else，注释里写的担心恰好就是代码缺的那一半。
            # 但上一版的 else 走得更远：它把整层归零。重开工程那一条路（关键点不随
            # 工程文件走，见 _project_build）一定会撞在这里，于是用户的一层瘦脸在
            # “保存→重开”之间悄悄消失——配方完整恢复是 CORE-001 的 then，不是“参数碰巧还在”。
            # 所以这里改成「待重挂」：值留着、built=False、报一条 defer 事件，关键点一回来就重建。
            if self._deform_intent():
                # 判据从“常驻那一份在不在”换成“用户的意图在不在”（PORTRAIT-004）：
                # 三层里任何一层有劲儿都要重挂，否则 `built=False` 而默认/覆盖还在的
                # 那一型会在重挂时被整段跳过——生效值非零而画面不动
                if self._precompute is None:
                    emit({"event": "engine_warn",
                          "warn": "会话重挂时没有关键点可重建形变层：滑块值与层级已存住，"
                                  "等下一次 precompute 自动重挂（不先清掉用户那一层）"})
                    self._deform_defer = any(abs(float(v)) > 0.0
                                             for v in self._deform["amounts"].values())
                    self._deform = dict(amounts=dict(self._deform["amounts"]), built=False)
                    self._emit_deform_state("defer", reason="没有关键点可重建单位场，已存住等重挂")
                else:
                    # 不补帧：调用方（换设备那一条）紧后就自己渲染并写 shm，
                    # 而会话刚迁移时 _write_current_frame 抱异常会把整个迁移打断
                    self._rebuild_deform_for_landmarks(self._precompute, write_frame=False)
            # 调色层：表与像素位置无关，重挂只是把同一份原件再上一次显存（33³ 实测 428 KB）。
            # 不重挂就是“会话迁了、调色没迁”：新会话里 lut is None，屏幕回到未调色，
            # 而宿主侧 status.lut 还停在上一条 payload——上报与实际双向错配。
            if self._lut is not None:
                try:
                    pipe.set_lut(self._lut, self._lut_amount)
                    self._lut_amount = float(pipe.lut_amount)
                except (LutError, RuntimeError, ValueError) as e:
                    from .custom_lut_asset import CustomCube
                    if isinstance(self._lut, CustomCube): raise
                    emit({"event": "engine_warn",
                          "warn": f"新会话重挂调色层失败，已整层清除（{type(e).__name__}）：{e}"})
                    self._lut = None
                    self._lut_amount = 1.0
            # 定向层（M3-b）：它不持有张量，所以“重挂”就是把同一组数重新提交一次。
            # 不提交就是“会话迁了、肤色滑块还在宿主侧的 0.6 但画面不动”——lut 上面
            # 那段注释写的担心，在这一层一模一样。
            if self._grade != (0.0, 0.0, 0.0, 1.0):
                try:
                    pipe.set_grade(self._grade[0], self._grade[1], self._grade[2],
                                   amount=self._grade[3])
                    self._grade = tuple(pipe.grade_params) + (float(pipe.grade_amount),)
                except (GradeError, RuntimeError, ValueError) as e:
                    emit({"event": "engine_warn",
                          "warn": f"新会话重提交肤色定向失败，已整层清除（{type(e).__name__}）：{e}"})
                    self._grade = (0.0, 0.0, 0.0, 1.0)
            # 裁剪/旋转（P0 lnx.crop.v1）：重挂只是把同一组数再提交一次。不提交就是
            # “会话迁了、明明裁过而画面满幅回来”，与上面 lut/grade/曝光同一条担心。
            # 走 pipe 而不走 self._vram：两者在这一段里恰好是同一个对象，但只有 pipe
            # 是“刚刚新建的那一个”——写成 self._vram 就是给以后把 adopt 拆出去的人埋雷。
            if self._crop_rect != (0.0, 0.0, 1.0, 1.0) or self._crop_rotation != 0.0:
                try:
                    pipe.set_geometry(self._crop_rect, self._crop_rotation)
                except Exception as e:
                    emit({"event": "engine_warn",
                          "warn": f"新会话重挂裁剪/旋转失败，已清除（{type(e).__name__}）：{e}"})
                    pipe.clear_geometry()
                    self._crop_rect = (0.0, 0.0, 1.0, 1.0)
                    self._crop_rotation = 0.0
            # 曝光层（P0）：不持有张量，重挂就是把同一组数重新提交一次。不提交就是
            # “会话迁了、滑杆还在 0.5 EV 但画面不动”，与上面 lut/grade 同一条担心。
            # 判据必须把 reference_k 也算进去：cmd_exposure 允许只给 reference_k（EV 与
            # 两个偏移全为 0），那时三元组还是中性值而白平衡已偏离默认光源。只看三元组
            # 就会“会话迁了、参考光源没迁”：新会话按默认 K 数渲染，而宿主侧滑块的位置
            # 说的是另一个数——与上面那段担心是同一个错误，只是藏在另一个键上。
            if (self._exposure != (0.0,) * 7 or self._exposure_ref_k is not None
                    or WB.has_picks(self._wb_options) or self._wb_options["algorithm"] == WB.CORRECTED):
                st = pipe.set_exposure(*self._exposure[:3], ref_k=self._exposure_ref_k,
                                       contrast=self._exposure[3], highlights=self._exposure[4],
                                       shadows=self._exposure[5], saturation=self._exposure[6],
                                       wb_options=self._wb_options)
                self._exposure_ref_k = float(st["exposure_reference_k"])
            # Curves are independent of LUTs and must survive every session rebuild.
            if not LEVELS.is_identity(self._levels): pipe.set_levels(self._levels)
            if not CURVES.is_identity(self._curves):
                pipe.set_curves(self._curves)  # fail visibly; never silently erase a recipe
            # 八色 HSL：与上面同一条“不提交就是会话迁了而画面回中性”。
            if self._hsl != (0.0,) * 24:
                pipe.set_hsl(self._hsl)  # propagate to transaction rollback; never erase silently
            # 换底层（M6）：遮罩张量活在那块卡上，新会话必须用存下的遮罩重新上传一次。
            # 不重挂就是“会话迁了、换底还在宿主侧但画面回到底图”——lut/grade 写的那段担心在这一层同样成立。
            from .common_background_source import rehang as rehang_common_background
            rehang_common_background(self,pipe,emit)
            # 局部调色（COLOR-004）：作用域与区域同样必须跟着会话走。不重挂就是“会话迁了、
            # 屏幕上却变成全图调色”，而 grade_done 还写着 brush——与上面 lut/grade 同一条担心。
            # skin 那一臂在这里可能被推迟（掩膜要 _rehang_precompute 之后才有），那里会再调一次。
            self._rehang_grade_scope(replayed_for="session_switch")
            # 眼牙层（PORTRAIT-009）：场活在卡上，新会话必须重画一次。没有关键点时
            # 它自己会转成 defer（存住参数），而不是静默归零——与上面形变同一条担心。
            self._rehang_enhance(replayed_for="session_switch", write_frame=False)
        emit({"event": "vram_ready", "device": str(pipe.device), "w": w, "h": h,
              "adopted": bool(adopt),
              "bytes_src": int(pipe.src_u8.numel() * pipe.src_u8.element_size()),
              "bytes_frame": int(pipe.frame_gpu.numel() * pipe.frame_gpu.element_size())})
        if adopt: ETH.sync_current(self); PDH.sync_current(self); CGA.sync(self); SCLA.sync(self); CEA.sync(self); PCA.sync(self)
        return pipe

    def _open_vram(self, w: int, h: int):
        """跑靶用的合成源图会话（不拥有全局会话，见 _attach_pipeline.adopt）。"""
        return self._attach_pipeline(test_frame(w, h, 0)[:, :, :3].copy(), adopt=False)

    # ------------------------------------------------------------ 文档状态（M5-a 底片条）
    # 「一份文档状态到底包含哪些字段」只有这一处名单。新加一层而不进来，切文档就会
    # 静默丢掉那一层 —— 那是本仓最贵的一族坑（「会话迁了、图层没迁」）的新变体。
    DOC_FIELDS = (*CDH.FIELDS, "_fabric_amount", "_strength", "_params", "_channel", "_repair_ops", "_redo_ops", "_op_seq",
                  "_light_ops", "_light_redo", "_light", "_deform", "_deform_defer",
                  "_deform_default", "_deform_overrides", "_lut",
                  "_lut_amount",
                  "_lut_preset", "_grade", "_grade_scope", "_grade_mask", "_local_masks", "_local_grade_layers", "_effect_recovery", "_manual_liquify", "_studio_background", "_id_background", "_id_background_bundle", "_optics", "_sky_replacement", "_blush_makeup_library", "_lipstick_library", "_eyeliner_library", "_eyelash_library", "_brow_makeup_library", "_lip_makeup", "_brow_shape", "_brow_shape_owner", "_nose_shape", "_nose_shape_owner", "_eye_shape", "_eye_shape_owner", "_mouth_shape", "_mouth_shape_owner", "_reference_color", "_reference_color_bundle", "_semantic_colour", "_semantic_colour_bundle", "_semantic_colour_mask_assets", "_body_pose_bank", "_bg",
                  "_enhance", "_enhance_defer",
                  "_precompute", "_precompute_backend", "_face_index", "_face_box",
                  "_face_explicit", "_face_manual",
         "_exposure",
         "_exposure_ref_k", "_primary_calibration", "_selective_colour", "_colour_editor", "_photo_grain", "_colour_grading", "_extended_tone", "_photo_detail", "_fringe_repair", "_wb_options", "_hsl", "_curves", "_levels", "_crop_rect", "_crop_rotation")
    # 代理档一变就作废的那些层：它们的坐标是**这一档代理帧**上的像素坐标。
    PROXY_BOUND = ("_channel", "_repair_ops", "_redo_ops", "_light_ops", "_light_redo",
                   "_deform", "_deform_defer", "_deform_default", "_deform_overrides",
                   "_bg", "_precompute", "_precompute_backend",
                   # 选型 index 是“那一次分析结果里的第几张”（PORTRAIT-003）：分析作废而
                   # index 还留着，下一次 precompute 完就会拿旧序号去对新名单——那正是
                   # “静默选了另一个人”的形状，与不选型一样错。
                   # 眼牙那一层的场画在这一档代理帧的坐标上（窗口是像素框），而 amounts
                   # 与脸盒是"用户改了主意才算变"的东西：作废的判据跟着场走，与 _deform 同例。
                   "_enhance",
                   "_face_index", "_face_box", "_face_explicit",
                   # 调色区域是代理帧像素坐标，作用域活在区域/掩膜之上：掩膜作废而
                   # 作用域还写着 brush/skin，下一帧就是一条取不到权重的异常。
                   "_grade_scope", "_grade_mask")
    # `_face_manual` **不在**上面这份名单里，这是决定而不是遗漏：那两份账存的是代理帧
    # 像素坐标/那一次分析的序号，而人工账存归一化脸盒，换代理档、换后端重算都仍指同一个
    # 人。把它一起作废就等于「重算一次分辨率，用户关掉的误检自己活了回来」——冻结件
    # （PORTRAIT-006 的 then）明确禁止的正是这个动作。

    def _fresh_doc_state(self) -> dict:
        """一张还没被人动过的图的起始状态。

        **加图层必须同时改这里**，不然就是本轮那个 KeyError：d3b 把 `_exposure` 加进了
        DOC_FIELDS 与 `_capture_state`，唯独没加进这份“新鲜状态”。名单守卫只比 `_capture_state`
        与 DOC_FIELDS，两边一起漏就照不出——而底片条里每张新图都要走 `_apply_state(_fresh_doc_state())`，
        第一次 load_image 就撞在 `st[k]` 上。dev venv 里那条路整批 skip（要 torch），装机的
        运行时 venv 才是唯一会走到这行的人。所以这份名单也上守卫，缺一个键当场响。

        这段原来是内联在 cmd_load_image 里的一串赋值，语义是「换图即清空」；那条守卫
        本身一条没错——旧图的掩膜/笔迹对新图没有任何意义。今天它多了一个身份：底片条
        里「这张图还没被调过」的定义。同一个口径写两处就会漂，所以抽成一份。
        """
        fresh = {"_fabric_amount": 0.0, "_strength": _clamp_strength(DEFAULT_STRENGTH),
                "_params": dict(radius=DEFAULT_RADIUS, eps=DEFAULT_EPS,
                                texture_radius=DEFAULT_TEXTURE_RADIUS,
                                broad_gain=DEFAULT_BROAD_GAIN, mid_gain=DEFAULT_MID_GAIN,
                                detail_gain=DEFAULT_DETAIL_GAIN),
                "_channel": None,
                "_repair_ops": [], "_redo_ops": [], "_op_seq": 0,
                "_light_ops": [], "_light_redo": [],
                "_light": dict(exposure=DEFAULT_DB_EXPOSURE, radius=DEFAULT_DB_RADIUS),
                "_deform": dict(amounts={k: 0.0 for k in KINDS}, built=False),
                # 待重挂标记与层一起走：换图/作废代理档时形变整层放下，标记也必须跟着清，
                # 不然下一次分析会把「上一张图的瘦脸」复活成这一张图上的一层。
                "_deform_defer": False,
                "_deform_default": {k: 0.0 for k in KINDS}, "_deform_overrides": [],
                "_lut": None, "_lut_amount": 1.0, "_lut_preset": None,
                "_grade": (0.0, 0.0, 0.0, 1.0),
                "_grade_scope": "all", "_grade_mask": None, "_local_masks": LM.empty(), "_local_grade_layers": LG.empty(), "_effect_recovery": ERS.empty(), "_manual_liquify": MLS.empty(), "_studio_background": SBS.empty(), "_id_background": IDS.empty(), "_id_background_bundle": None, "_optics": OPS.empty(), "_sky_replacement": SKS.empty(), "_blush_makeup_library": BLUSHLIB.empty(), "_lipstick_library": LIPSTICKLIB.empty(), "_eyeliner_library": EYELINERLIB.empty(), "_eyelash_library": EYELASHLIB.empty(), "_brow_makeup_library": BROWMAKEUPLIB.empty(), "_lip_makeup": LIPS.neutral(), "_brow_shape": BROWS.neutral(), "_brow_shape_owner": None, "_nose_shape": NOSES.neutral(), "_nose_shape_owner": None, "_eye_shape": EYES.neutral(), "_eye_shape_owner": None, "_mouth_shape": MOUTHS.neutral(), "_mouth_shape_owner": None, "_reference_color": RCS.empty(), "_reference_color_bundle": None, **self._semantic_fields(), **self._body_fields(),
                "_enhance": dict(amounts={k: 0.0 for k in ENH.AMOUNT_KEYS}, built=False, box=None),
                "_enhance_defer": False,
                "_bg": dict(active=False, matte=None, bg=None, backend=None,
                             tol=None, softness=None),
                "_precompute": None, "_precompute_backend": None,
                # 多人图里“正在编辑哪一张”的选择（PORTRAIT-003）。`_face_explicit` 与
                # `_face_index` 成对：一张脸没选过时，多人图的单脸作用域操作整条拒（SCOPE-001），
                # 选过之后才放行。只存 index 不存“是不是人选的”，下次就能拿默认 0 冒充选定。
                # `_face_box` 是那一张脸的**身份**：检测器的返回顺序不是人能预期的，
                # 重算/重开工程后拿旧序号对新名单就是一次静默选型，所以认脸靠脸盒。
                "_face_index": 0, "_face_box": None, "_face_explicit": False,
                # 一张新图上「用户关过谁、补过谁」当然都是空。这份默认必须是**新字典
                # 新列表**，不能是类级常量：两张图共用一个 list，关掉 A 图那一只误检就
                # 会把 B 图同位置的脸也关掉（与 `_deform["amounts"]` 整份新抄同一条理由）
                "_face_manual": {"disabled": [], "added": []},
                "_exposure": (0.0,) * 7, "_extended_tone": ETS.default(), "_photo_detail": PDS.default(), "_fringe_repair": FRS.neutral(), "_photo_grain": PGS.neutral(), "_colour_grading": CGS.neutral(), "_primary_calibration": PCS.neutral(), "_selective_colour": SCSL.neutral(), "_colour_editor": CES.neutral(), "_exposure_ref_k": None, "_wb_options": WB.default_options(),
                "_hsl": (0.0,) * 24, "_curves": CURVES.default_curves(), "_levels": LEVELS.default_levels(),
                "_crop_rect": (0.0, 0.0, 1.0, 1.0), "_crop_rotation": 0.0,
                # 掩膜/笔迹/形变场都活在**那一档代理尺寸**上，所以尺寸也是状态的一部分。
                "_proxy": None}
        # 名单守卫的另一半：起始状态与 _capture_state 必须覆盖同一批字段。
        # 只守一侧等于把“新图层忘了登记进默认值”这件事留给运行时去撞
        fresh.update(CDH.neutral())
        assert set(fresh) == set(self.DOC_FIELDS) | {"_proxy"}, \
            "起始状态名单与 DOC_FIELDS 漂移了（新图层没给默认值）"
        return fresh

    def _capture_state(self) -> dict:
        """把 live 字段抄成一份可存的字典。容器一律新抄：存进去的状态与 live 字段共享
        同一个 list，下一次 append 会同时改掉两个文档的状态——查起来就像「切了一次文档，
        上一张的笔迹自己多了一笔」。"""
        st = {"_fabric_amount": float(self._fabric_amount), "_strength": float(self._strength), "_channel": self._channel,
              "_params": dict(self._params), "_light": dict(self._light),
              "_deform": {"amounts": dict(self._deform["amounts"]),
                          "built": bool(self._deform["built"])},
              "_deform_defer": bool(self._deform_defer),
              "_deform_default": dict(self._deform_default),
              # 覆盖那份整份新抄：里面的 dict 不能与 live 共享（同 _capture_state 那条理由）
              "_deform_overrides": [{"box": tuple(o["box"]), "amounts": dict(o["amounts"])}
                                    for o in self._deform_overrides],
              "_repair_ops": list(self._repair_ops), "_redo_ops": list(self._redo_ops),
              "_op_seq": int(self._op_seq),
              "_light_ops": list(self._light_ops), "_light_redo": list(self._light_redo),
              # 调色表是只读原件（set_lut 会把它拷成会话张量），多份文档共享同一个数组
              # 不会互相改；真要出现就地写，这里就得改成拷贝。
              "_lut": self._lut, "_lut_amount": float(self._lut_amount),
              "_lut_preset": self._lut_preset, "_grade": tuple(self._grade),
              "_grade_scope": str(self._grade_scope), "_grade_mask": self._grade_mask, "_local_masks": LM.check(self._local_masks), "_local_grade_layers": LG.check(self._local_grade_layers), "_effect_recovery": ERS.check(self._effect_recovery), "_manual_liquify": MLS.check(self._manual_liquify), "_studio_background": SBS.check(self._studio_background), "_id_background": IDS.check(self._id_background), "_id_background_bundle": self._id_background_bundle, "_optics": OPS.check(self._optics), "_sky_replacement": SKS.check(self._sky_replacement), "_blush_makeup_library": BLUSHLIB.capture(self), "_lipstick_library": LIPSTICKLIB.capture(self), "_eyeliner_library": EYELINERLIB.capture(self), "_eyelash_library": EYELASHLIB.capture(self), "_brow_makeup_library": BROWMAKEUPLIB.capture(self), "_lip_makeup": LIPS.check(self._lip_makeup), "_brow_shape": BROWS.check(self._brow_shape), "_brow_shape_owner": self._brow_shape_owner, "_nose_shape": NOSES.check(self._nose_shape), "_nose_shape_owner": self._nose_shape_owner, "_eye_shape": EYES.check(self._eye_shape), "_eye_shape_owner": self._eye_shape_owner, "_mouth_shape": MOUTHS.check(self._mouth_shape), "_mouth_shape_owner": self._mouth_shape_owner, "_reference_color": RCS.check(self._reference_color), "_reference_color_bundle": self._reference_color_bundle, **self._semantic_capture(), **self._body_fields({"_body_pose_bank":self._body_pose_bank}),
              # 整份新抄：amounts 那个 dict 不能与 live 共享（同 _capture_state 头部那条理由，
              # 两个文档共用一个 dict，下一笔 set 会同时改掉两份状态）
              "_enhance": {"amounts": dict(self._enhance["amounts"]),
                           "built": bool(self._enhance["built"]),
                           "box": (None if self._enhance.get("box") is None else
                                   tuple(float(v) for v in self._enhance["box"]))},
              "_enhance_defer": bool(self._enhance_defer),
              "_photo_grain": PGS.check(self._photo_grain), "_colour_grading": CGS.check(self._colour_grading), "_primary_calibration": PCS.check(self._primary_calibration), "_selective_colour": SCSL.check(self._selective_colour), "_colour_editor": CES.check(self._colour_editor), "_extended_tone": ETS.check(self._extended_tone), "_photo_detail": PDS.check(self._photo_detail), "_fringe_repair": FRS.check(self._fringe_repair), "_exposure": tuple(self._exposure), "_exposure_ref_k": self._exposure_ref_k,
              "_wb_options": WB.check_options(self._wb_options),
              "_hsl": tuple(self._hsl), "_curves": CURVES.check_curves(self._curves), "_levels": self._levels,
              "_crop_rect": tuple(self._crop_rect), "_crop_rotation": float(self._crop_rotation),
              "_bg": dict(self._bg),
              "_precompute": self._precompute, "_precompute_backend": self._precompute_backend,
              "_face_index": int(self._face_index), "_face_explicit": bool(self._face_explicit),
              "_face_box": (None if self._face_box is None
                             else tuple(float(v) for v in self._face_box)),
              # 人工账整份新抄（列表不共享）：切文档时两份状态共用一个 list，下一次
              # `face disable` 会同时改掉另一张图的账——那是「在 A 图关的脸出现在 B 图」
              "_face_manual": {"disabled": [tuple(float(v) for v in b) for b in
                                            (self._face_manual or {}).get("disabled") or []],
                               "added": [tuple(float(v) for v in b) for b in
                                         (self._face_manual or {}).get("added") or []]},
              "_proxy": ((int(self._vram.h), int(self._vram.w))
                         if (self._vram is not None and self._image_loaded) else None)}
        # 名单与实际字段漂移了要当场响，不要“新图层静静切不回来”
        st.update(CDH.fields(self))
        assert set(st) == set(self.DOC_FIELDS) | {"_proxy"}, "文档状态名单与实际字段漂移了"
        return st

    def _apply_state(self, st: dict) -> None:
        # Reject broken/unknown active AND redo records before any live mutation.
        for key in ("_repair_ops", "_redo_ops"):
            validate_repair_ops(st.get(key, []), shape=st.get("_proxy"))
        from .creative_derived_repairs import validate_stacks
        validate_stacks(st)
        from .creative_derived_global_recovery import validate_state as validate_global_recovery
        validate_global_recovery(st)
        from .creative_derived_studio import validate_state as validate_studio
        validate_studio(st)
        from .creative_derived_sky import validate_state as validate_sky
        validate_sky(st)
        from .creative_derived_id_background import validate_state as validate_id
        validate_id(st)
        # Validate WB and compile before changing any live field.
        st = {**st, "_photo_grain": PGS.from_state(st), "_colour_grading": CGS.from_state(st), "_primary_calibration": PCA.admit(PCS.from_state(st)), "_selective_colour": SCSL.from_state(st), "_colour_editor": CES.from_state(st), "_extended_tone": ETS.check(st.get("_extended_tone")), "_photo_detail": PDS.check(st.get("_photo_detail")), "_fringe_repair": FRS.from_state(st), **self._semantic_restore(st), **self._body_fields(st), "_fabric_amount": FABRIC.check_amount(st.get("_fabric_amount", 0.0)), "_local_masks": LM.check(st.get("_local_masks")), "_local_grade_layers": LG.check(st.get("_local_grade_layers")), "_effect_recovery": ERS.check(st.get("_effect_recovery")), "_manual_liquify": MLS.check(st.get("_manual_liquify")), "_studio_background": SBS.check(st.get("_studio_background")), "_id_background": IDS.check(st.get("_id_background")), "_id_background_bundle": st.get("_id_background_bundle"), "_optics": OPS.check(st.get("_optics")), "_sky_replacement": SKS.check(st.get("_sky_replacement")), "_blush_makeup_library": BLUSHLIB.check(st["_blush_makeup_library"]) if "_blush_makeup_library" in st else BLUSHLIB.empty(), "_lipstick_library": LIPSTICKLIB.check(st["_lipstick_library"]) if "_lipstick_library" in st else LIPSTICKLIB.empty(), "_eyeliner_library": EYELINERLIB.check(st["_eyeliner_library"]) if "_eyeliner_library" in st else EYELINERLIB.empty(), "_eyelash_library": EYELASHLIB.check(st["_eyelash_library"]) if "_eyelash_library" in st else EYELASHLIB.empty(), "_brow_makeup_library": BROWMAKEUPLIB.check(st["_brow_makeup_library"]) if "_brow_makeup_library" in st else BROWMAKEUPLIB.empty(), "_lip_makeup": LIPS.check(st.get("_lip_makeup")), "_brow_shape": BROWS.check(st.get("_brow_shape")), "_brow_shape_owner": st.get("_brow_shape_owner"), "_nose_shape": NOSES.check(st.get("_nose_shape")), "_nose_shape_owner": st.get("_nose_shape_owner"), "_eye_shape": EYES.check(st.get("_eye_shape")), "_eye_shape_owner": st.get("_eye_shape_owner"), "_mouth_shape": MOUTHS.check(st.get("_mouth_shape")), "_mouth_shape_owner": st.get("_mouth_shape_owner"), "_reference_color": RCS.check(st.get("_reference_color")), "_reference_color_bundle": st.get("_reference_color_bundle")}
        st = {**st, **CDH.restore_fields(st)}
        st = WB.normalize_state(st)
        WB.prepare_state(st)
        # Old projects predate curves. Validate/deep-copy before changing any live field.
        st = {**st, "_curves": CURVES.check_curves(st.get("_curves")), "_levels": LEVELS.check_levels(st.get("_levels")),
              "_hsl": HSL_RECIPE.normalize_state(st.get("_hsl", HSL_RECIPE.NEUTRAL))}
        CDH.rotate(self)
        for k in self.DOC_FIELDS:
            v = st[k]                 # 缺键就是名单漂移，让它响
            setattr(self, k, v)
        # 容器重新抄一遍：存着的状态不能与 live 字段共用同一个 list/dict（理由同 _capture_state）
        self._params = dict(self._params)
        self._light = dict(self._light)
        self._deform = {"amounts": dict(self._deform["amounts"]), "built": bool(self._deform["built"])}
        # 工程档里回来的是 JSON 布尔/缺键（1.3.0 之前的配方没这一格）：归一成 bool，
        # 缺就当 False。拿 1 冒充 True 会让「有没有待重挂那一层」这句判据时灵时不灵。
        self._deform_defer = bool(self._deform_defer)
        if not any(abs(float(v)) > 0.0 for v in self._deform["amounts"].values()):
            # 全零的滑块值不构成一层：标记留着只会在下一次分析后报一个「重建了个空层」
            self._deform_defer = False
        # 层级那两份（PORTRAIT-004）从 JSON 回来是 list/数组：键与类型一律归一，
        # 不然"有没有覆盖"的判据会拿 ["0.5"] 与 0.5 比出两个答案
        self._deform_default = {k: float(self._deform_default.get(k, 0.0) or 0.0)
                                for k in KINDS}
        self._deform_overrides = [{"box": tuple(float(v) for v in o.get("box") or ()),
                                   "amounts": {k: float(v) for k, v in (o.get("amounts") or {}).items()
                                               if k in KINDS}}
                                  for o in (self._deform_overrides or [])
                                  if isinstance(o, dict) and o.get("box")]
        self._repair_ops = list(self._repair_ops)
        self._redo_ops = list(self._redo_ops)
        self._light_ops = list(self._light_ops)
        self._light_redo = list(self._light_redo)
        self._grade = tuple(self._grade)
        # 作用域从 JSON 回来是字符串，缺键的旧工程档（1.2.0 之前存的）没有这一项：
        # 认「全图」而不是拿 None 去和 vram 的名单比。区域是 numpy 原件或 None，
        # 与 _bg 的遮罩同一条路（project 的资产编码器负责把 ndarray 落成资产）。
        self._grade_scope = str(self._grade_scope or "all")
        # 眼牙那一份从 JSON 回来时：amounts 可能是 list/字符串/缺键，box 可能是数组，
        # built/defer 可能是 None。一律归一，判据（"有没有这一层"）不许时灵时不灵
        _en = self._enhance or {}
        _wrinkle = WSTATE.check(_en.get("amounts") or {})
        _am = {}
        for _k in ENH.AMOUNT_KEYS:
            if _k in _wrinkle:
                _am[_k] = _wrinkle[_k]
                continue
            try:
                _am[_k] = float((_en.get("amounts") or {}).get(_k, 0.0) or 0.0)
            except (TypeError, ValueError):
                _am[_k] = 0.0
        _box = _en.get("box")
        self._enhance = {"amounts": _am, "built": bool(_en.get("built")),
                         "box": (None if not _box else tuple(float(v) for v in _box))}
        self._enhance_defer = bool(self._enhance_defer)
        if not WSTATE.active_enhance(_am):
            # 全零不构成一层：defer 留着只会在下一次分析后报一个"画了个空场"
            self._enhance_defer = False
        self._bg = dict(self._bg)
        # 从项目文件回来的配方里，元组一律是 JSON 数组。`_grade` 早就在这里归一回，
        # 而 crop/exposure 不归一就会漂：重挂判据与“中性”判据比的都是元组字面量，
        # list != tuple 永真 → “没点火的层”被当成“已点火”，而画面确实没变。
        # 这是双向错配的另一格：不是图层没迁，是类型让判据说了谎。
        self._crop_rect = tuple(float(x) for x in self._crop_rect)
        self._crop_rotation = float(self._crop_rotation)
        self._exposure = (tuple(float(x) for x in self._exposure) + (0.0,) * 7)[:7]
        self._exposure_ref_k = None if self._exposure_ref_k is None \
            else float(self._exposure_ref_k)
        self._strength = _clamp_strength(self._strength)
        # 从 JSON 回来的选型：数字可能是 float/字符串（旧工具链手写工程档），布尔可能没这一格。
        # 不归一就会出现“选定了而引擎不认”：判据比的是 `is True`，而那里躺着个 1。
        self._face_index = int(self._face_index or 0)
        self._face_box = None if self._face_box is None \
            else tuple(float(v) for v in self._face_box)
        self._face_explicit = bool(self._face_explicit)
        # 人工账从工程档回来是「列表的列表」，元素可能是 float/字符串/长度不对的残框
        # （手写档或上一版半成品）。归一成 4 元 float 盒并丢掉不成形的那些：留一条 3 元
        # 残框，下一次按盒认人时 zip 会静默截断成前三维，把另一个人认成「你关掉的那一个」
        self._face_manual = {"disabled": [b for b in (self._manual_box(v) for v in
                                                      (self._face_manual or {}).get("disabled") or [])
                                         if b is not None],
                             "added": [b for b in (self._manual_box(v) for v in
                                                   (self._face_manual or {}).get("added") or [])
                                       if b is not None]}
        # 层级合成（PORTRAIT-004）必须在选型归一之后：合成认的是**脸盒**身份，
        # 顺序反过来就会拿旧名单里的第 0 张去查覆盖，把 A 的覆盖当成 B 的
        if not any(abs(float(v)) > 0.0 for v in self._deform_default.values()) \
                and not self._deform_overrides:
            # 老配方的迁移（1.4.0 之前没有这两格）：那一版没有“逐张覆盖”这一层，存着的
            # `amounts` 只能来自“对所有人一样的那一层”，所以把它升成默认。不迁就会在
            # 重开老工程时把用户的形变层整个抹掉——那是比“少一层”更坏的一种错
            if any(abs(float(v)) > 0.0 for v in self._deform["amounts"].values()):
                self._deform_default = {k: float(self._deform["amounts"].get(k, 0.0))
                                        for k in KINDS}
        # 生效值只有一个出处：从两份层级合成，不把存下来的那份 amounts 当真相
        # （它是上一次合成的结果，而脸盒可能已经换了、层级可能来自手改的工程档）
        self._deform["amounts"] = self._effective_deform_amounts()
        self._deform_defer = (not self._deform["built"]) and any(
            abs(float(v)) > 0.0 for v in self._deform["amounts"].values())

    def _drop_proxy_layers(self, st: dict, why: str) -> dict:
        """代理档变了 → 只留下逐点的那几层，按像素坐标成立的全部作废。

        不作废就是拿一张 800×1000 的掩膜去贴 1152×720 的会话：库层会按名字把通道递出来，
        render 时才撞尺寸，而那时报表上已经写着「有 skin 通道」。宁可多啰嗦一句也要说清。
        """
        out = dict(st)
        for k in self.PROXY_BOUND:
            out[k] = self._fresh_doc_state()[k]
        from .common_background_source import preserve_proxy_recipe
        preserve_proxy_recipe(st,out)
        if st.get("_creative_base") is not None:
            out["_channel"] = st.get("_channel")  # Preserve scope intent; never broaden missing skin masks.
        if st.get("_grade_scope") == "objects": out["_grade_scope"] = "objects"
        out["_op_seq"] = 0
        out["_proxy"] = None
        emit({"event": "engine_warn", "warn": f"{why}：按像素坐标成立的层（掩膜/笔迹/形变）已全部丢弃，"
                                              "逐点层（磨皮参数/调色表/肤色定向）原样保留"})
        return out

    def _index_of(self, path, document_id=None) -> int:
        from .virtual_copy_session import index_of
        return index_of(self._docs, path, document_id)

    def _document_versions(self):
        from .document_versions import DocumentVersions
        owner=self.__dict__.get("_document_version_owner")
        if owner is None:owner=DocumentVersions();self._document_version_owner=owner
        return owner

    def _fence_current_document(self):
        index=getattr(self,"_doc_index",-1);rows=getattr(self,"_docs",[])
        if 0<=index<len(rows):self._document_versions().advance(rows[index])

    def _new_row(self, path: str, *, state: dict | None = None, budget: int | None = None) -> dict:
        m = S.doc_meta(path)
        row = {**m, "path": os.path.abspath(path), "state": state or self._fresh_doc_state(),
                "budget": budget, "thumb": None, "thumb_error": None, "opened": False, "_optics_new_import": state is None, "_people_new_import": state is None,
                "undo": [], "redo": [],
                # 项目层的三个字段（LNX-P0-PROJECT / CORE-001、CORE-007）：标签与回收站
                # 是工程记录，不是对原图动手。`fingerprint` 只在项目保存或打开时才算
                # （全文件哈希是几十毫秒级的一次性成本，不藏在 load_image 的首帧里）。
                "tags": [], "label": None, "trashed": False, "fingerprint": None,
                "w": None, "h": None, "src_w": None, "src_h": None,
                # 挑图建议（派生旁注）：一次分析的完整读数与折出来的建议。它随会话活、
                # 不随工程文件走（理由同 _precompute：是算出来的，不是用户画的）。
                "pick": None, "pick_error": None}
        from .export_destination_import import origin
        row['import_origin'] = origin(row['path'])
        self._document_versions().version(row)
        library_file_identity(row)
        return row

    def _remember_current(self) -> None:
        """把 live 状态存回当前文档那一格。底片条的一切意思都在这一步：不存就是
        「切走再切回来，调的全没了」。"""
        if 0 <= self._doc_index < len(self._docs) and self._image_loaded:
            from .virtual_copy_people import remember
            remember(self)
            self._docs[self._doc_index]["state"] = self._capture_state()
            # 历史跟着状态走：只存状态不存栈，切回来会"画面带着一笔而撤销按钮是灰的"
            self._docs[self._doc_index]["undo"] = list(self._undo)
            self._docs[self._doc_index]["redo"] = list(self._redo)
            self._docs[self._doc_index]["_history_owned"] = True

    # ------------------------------------------------------------ 全局撤销/重做（M5-b）
    # 一步 = 一次手势，不是一条命令：拖强度滑块一口气发五十条，用户按一次 Ctrl+Z
    # 该退回的是"开始拖之前"，而不是"上一帧的值"。
    HISTORY_MAX = 64
    HISTORY_GROUP_MS = 700
    # 快照里不进历史的两项。理由有两条，都是硬的：① 人脸预计算是"检测"不是"修图"，
    # 撤销不该把掩膜退回去（也没有任何用户动作期望它回去）；② 它是几 MB 的 numpy 原件，
    # 64 份快照会把几百 MB 内存钉在进程里。图层与参数照样进。
    HISTORY_SKIP = ("_precompute", "_precompute_backend")
    # 哪些命令算"编辑"。判定只在这一个名单里，推送点也只有分发器一处：
    # 六个 cmd_* 里各插一次 push 的下场可以预见——第七层加进来时总有人忘。
    # exposure 就在本轮被"总有人忘"忘过一次：它在 DOC_FIELDS 里（切文档、存工程都带得走），
    # 却不在这份名单里，于是拖完曝光按撤销——参数纹丝不动，而 UI 上没有任何一处会说"为什么
    # 撤销不了"（CORE-006 的新用例把它响出来了）。加一层时要同时改这里与 DOC_FIELDS，
    # 而 test_undo_redo_restores_recipe… 就是那个让人不能只改一边的守卫。
    EDIT_CMDS = ("fringe_repair", "common_background", "set_strength", "inpaint", "source_patch", "clone_stamp", "local_masks", "effect_recovery", "manual_liquify", "studio_background", "optics", "sky_replacement", "light", "deform", "lut", "grade", "background",
                 "crop", "exposure", "white_balance", "color_picker", "hsl", "curves", "levels", "preset", "batch", "face", "enhance", "lip_makeup", "brow_shape", "nose_shape", "eye_shape", "mouth_shape", "people", "hair_colour", "fabric")
    # preset/batch 也在这份名单里，而且不是“凑数”：套一次预设必须能一次 Ctrl+Z 退回去
    # （逐条命令各自入栈会得到“一次预设 = 四五步撤销”，而 UI 上看不出为什么），
    # 而 batch 改的就是活动文档的配方——不在这里它就会“同步完了而徽章不亮”。
    HISTORY_ACTIONS = HC.ACTIONS

    def _history_capture(self) -> dict:
        """抄一份可进历史的文档状态（= 文档状态去掉预计算那两项）。"""
        st = self._capture_state()
        for k in self.HISTORY_SKIP:
            del st[k]
        st["_people_history"]=self._people_history_capture()
        return st

    def _history_apply(self, snap: dict) -> None:
        """装回一份快照：预计算保持当前这一份，其余整份覆盖。"""
        snap=self._body_history_restore(snap)
        st = self._capture_state()
        self._people_history_apply(snap.get("_people_history"),snap.get("_people_transition"),source_state=snap)
        self._apply_state({**st, **snap})
        from .creative_derived_source import restore_history_source
        restore_history_source(self)
        # 选型与关键点必须是一对：`_precompute` 不进历史快照而 `_face_index` 进（PORTRAIT-003）。
        # 不重放这一格就会“状态说在改 0 号、画面在改 1 号”——两张脸都确实被推过，看不出来。
        # 拿它放在 cmd_history 里是第二份出处：回滚那一条臂会漏掉。
        self._replay_face_view()

    def _hist_sig(self, st: dict) -> str:
        return history_policy.state_signature(st)

    @staticmethod
    def _history_group(name: str, msg: dict) -> str:
        return history_policy.command_group(name, msg)

    def _history_guard(self, action: str):
        # History's original guard intentionally differs from _guard_editable.
        if self.bench is not None and self.bench.is_alive():
            return f"跑靶进行中，拒绝 history {action}：先 bench_stop"
        if self._export is not None and self._export.is_alive():
            return f"导出进行中，拒绝 history {action}：等 export_done"
        if not self._image_loaded or self._vram is None or self._src_rgb is None:
            return "尚未 load_image，没有可撤销的会话"
        return None

    def _history_restore_frame(self, snap: dict, mode: str):
        self._history_apply(snap)
        self._attach_pipeline(self._src_rgb, adopt=True)
        self._ensure_shm(self._vram.w, self._vram.h)
        if self._precompute is not None:
            self._rehang_precompute(replayed_for=mode)
        frame = self._write_current_frame(mode)
        CDH.publish_geometry(self, emit)
        return frame

    def _history_controller(self):
        controller = self.__dict__.get("_live_history")
        if controller is None:
            controller = HC.HistoryController(HC.HistoryPorts(
                capture=lambda: self._history_capture(),
                signature=lambda snap: self._hist_sig(snap),
                restore_frame=lambda snap, mode: self._history_restore_frame(snap, mode),
                guard=lambda action: self._history_guard(action),
                remember_current=lambda: self._remember_current(),
                status=lambda: self.doc_state(),
                mark_dirty=lambda: setattr(self, "_project_dirty", True),
                note_edit=lambda: LQ.note_edit(self)),
                emit=lambda event: emit(event), clock=lambda: monotonic_ns(),
                limit=self.HISTORY_MAX, group_ms=self.HISTORY_GROUP_MS)
            self._live_history = controller
        controller.limit = self.HISTORY_MAX
        controller.group_ms = self.HISTORY_GROUP_MS
        return controller

    def _history_record(self, group: str, before: dict, *, coalesce: bool = True) -> None:
        return self._history_controller().record(group, before, coalesce=coalesce)

    def _history_report(self) -> dict:
        return self._history_controller().report()

    def _history_bind(self, row: dict | None) -> None:
        return self._history_controller().bind(row)

    def cmd_creative_document(self, p: dict):
        return CDH.handle(self, p, emit)

    def cmd_history(self, p: dict):
        return self._history_controller().handle_command(p)

    # Session/embedding compatibility: these aliases never duplicate live stacks.
    _undo = property(lambda self: self._history_controller().undo,
        lambda self, value: setattr(self._history_controller(), "undo", value))
    _redo = property(lambda self: self._history_controller().redo,
        lambda self, value: setattr(self._history_controller(), "redo", value))
    _hist_group = property(lambda self: self._history_controller().group,
        lambda self, value: setattr(self._history_controller(), "group", value))
    _hist_group_ns = property(lambda self: self._history_controller().group_ns,
        lambda self, value: setattr(self._history_controller(), "group_ns", value))

    # ------------------------------------------------------------ 真图导入
    def cmd_load_image(self, p: dict):
        """导入（或从底片条切回）一张真图：解码 → 代理帧 → 常驻显存 → 出第一帧。

        解码耗时不藏在帧里：它是一次性成本，与拖滑块时的逐帧成本完全不同量级，
        混在一起量就分不出“导入慢”还是“交互慢”。

        切回一张已经在底片条里的图不是“导入一张新图”：先把当前这份状态存回它那一格，
        再把目标那一格装回来。层不写第二份重放代码——常驻会话本来就要在
        `_attach_pipeline` 里按引擎侧字段重放一遍（换设备那条路走的也是它），文档切换
        只需要在那之前把字段装对。
        """
        from .decode import PROXY_PIXELS, clamp_budget, is_raw, load_rgb

        # 跑靶线程还在写那块双缓冲：此时换图会 close/unlink 它正在写的 shm，
        # 线程会在已失效的 mmap 上抱错，产出一份“跑了半截但 frames=600”的数。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝换图：先 bench_stop"})
            return
        # 导出线程正拿着上一张图的笔迹与关键点在跑满幅：此时换图会把“当前文档”
        # 这张纸从它脚下抽掉，而它报出去的 skipped 里写的是旧文档。
        if self._export is not None and self._export.is_alive():
            emit({"event": "error", "error": "导出进行中，拒绝换图：等 export_done"})
            return
        try:
            selected = self._index_of(p["path"], p.get("document_id"))
            if selected >= 0 and self._docs[selected].get("trashed"):
                raise ValueError("请先恢复回收站文档")
        except ValueError as error:
            emit({"event":"error","error":str(error)}); return
        # Validate before decoding, preview publication, or switching recipe/history.
        # A rejected import must leave the current document intact.
        strength = (_clamp_strength(p["strength"])
                    if p.get("strength") is not None else None)
        budget = clamp_budget(p.get("max_px") or self._proxy_budget or PROXY_PIXELS)
        t0 = monotonic_ns()
        device_prepare_ms = 0.0
        # Existing sessions retain the old migration ordering: migrating after
        # publishing a new preview could overwrite it with the previous image.
        # Cold imports instead show their camera preview before torch/GPU warmup.
        requested_device = p.get("device")
        cold_device = requested_device is not None and not self._image_loaded
        if requested_device is not None and not cold_device:
            device_start = monotonic_ns()
            self.cmd_set_device({"device": requested_device})
            device_prepare_ms = (monotonic_ns() - device_start) / 1e6
        # RAW 先推一帧相机内嵌预览：真解码那一张要几百毫秒，而那张全清 JPEG 搬回来只要
        # 几毫秒——视口这几百毫秒不该是黑的。常驻层/预计算/历史栈仍然只认下面
        # 真解码那一张（分界规则在 decode.py），这一帧不参与任何编辑语义。
        self._preview_info = None
        if is_raw(p["path"]):
            self._preview_info = self._push_preview_frame(p["path"], budget, str(t0))
        if cold_device:
            device_start = monotonic_ns()
            self.cmd_set_device({"device": requested_device})
            device_prepare_ms = (monotonic_ns() - device_start) / 1e6
        try:
            source_stamp = LM.file_stamp(p["path"])
            d = load_rgb(p["path"], budget, device=self._effective_device())
            if selected >= 0:
                d = CDH.decoded_for_state(d, self._docs[selected]["state"], max_pixels=budget)
            if source_stamp != LM.file_stamp(p["path"]): raise ValueError("Source changed during decode")
        except Exception as e:
            tail = "（视口上那一张是相机内嵌预览，编辑没生效）" if self._preview_info else ""
            emit({"event": "error", "error": f"导入失败({type(e).__name__}): {e}{tail}"})
            return
        # Decoding succeeded; invalidate the old edit token before any recipe switch.
        # A later attach/render failure must never authorize edits with the old photo ID.
        self._load_id = ""
        self._proxy_budget = budget     # 下一次切文档默认沿同一档代理（会话级，见上面注释）
        self._preset_last = None        # 换文档了：“这张当前是哪个预设”不能跟着跳过去
        self._remember_current()
        idx = self._index_of(p["path"], p.get("document_id"))
        if idx < 0:
            self._docs.append(self._new_row(str(p["path"]), budget=budget))
            idx = len(self._docs) - 1
            row = self._docs[idx]
            self._apply_state(row["state"])           # 新格子 = 出厂默认，等于原来的“清空”
            existed = False
        else:
            row = self._docs[idx]
            row["budget"] = budget
            # “这一格存过状态”才是切回来与第一次开的唯一区分：扫描刚建的格子有路径
            # 但还没开过，拿它当“切回来”会把宿主要的 precompute 整步跳掉。
            existed = bool(row["opened"])
            st = row["state"]
            if st.get("_proxy") and (int(d.h), int(d.w)) != tuple(st["_proxy"]):
                self._document_versions().advance(row)
                st = self._drop_proxy_layers(
                    st, why=f"这张图上次开在 {st['_proxy'][1]}×{st['_proxy'][0]}，"
                            f"这次按代理预算解出 {d.w}×{d.h}")
                # 快照里的笔迹也是按旧档像素坐标成立的，留着就是一次"撤销能撤销出半截画面"
                row["undo"], row["redo"] = [], []
                emit({"event": "engine_warn",
                      "warn": "这张图的历史也一并清了：快照里的层按旧代理档的像素坐标成立"})
            self._apply_state(st)
        row["_local_source_stamp"] = source_stamp
        row.update(src_w=d.src_w, src_h=d.src_h)
        self._doc_index = idx
        from .virtual_copy_people import activate
        activate(self, row)
        self._history_bind(row)         # 这一格自己的撤销/重做栈
        self._doc_path = os.path.abspath(str(p["path"]))   # 导出默认目标；只有导成功才记账
        return self._open_session(d, p, t0=t0, strength=strength, switched=existed,
                                  device_prepare_ms=device_prepare_ms)

    def _push_preview_frame(self, path: str, budget: int, document_id: str) -> dict | None:
        """RAW 首帧：相机内嵌预览（只填浏览/首屏那个槽位，见 decode.py 顶部的分界规则）。

        内嵌预览比代理档小时，这里不放大：宿主会先按预览尺寸挂一块 shm，真解码
        落地时再换档（两条都是既有的 shm_ready 通路，计数重置已在宿主里做过）。把小预览
        放大成代理尺寸看起来“只发一次事件”，但那是我们编的像素，不是相机给的。

        这一帧不进会话：不建常驻张量、不动历史栈、不拿去做任何导出。
        """
        import numpy as np
        from .decode import load_preview
        try:
            pv = load_preview(path, budget)
        except Exception as e:                  # 预览通道任何意外都不该挡住导入本身
            emit({"event": "engine_warn", "warn": f"内嵌预览取失败：{type(e).__name__}: {e}"})
            return None
        if pv is None:
            return None
        rgba = np.empty((pv.h, pv.w, 4), dtype=np.uint8)
        rgba[:, :, :3] = pv.rgb
        rgba[:, :, 3] = 255
        shm = self._ensure_shm(pv.w, pv.h)
        with self._wlock:
            seq, t_emit, slot = shm.write_frame(rgba, presentation=self._frame_presentation(document_id, (pv.w,pv.h), "preview"))
        info = {"w": int(pv.w), "h": int(pv.h), "src_w": int(pv.src_w), "src_h": int(pv.src_h),
                "ms": round(float(pv.t_total_ms), 3), "seq": int(seq)}
        emit({"event": "preview_frame", "path": path, **info})
        emit({"event": "frame", "seq": info["seq"], "slot": slot, "t_emit_ns": t_emit,
              "w": shm.w, "h": shm.h, "mode": "preview"})
        return info

    def _open_session(self, d, p: dict, *, t0: int, strength: float | None, switched: bool,
                      device_prepare_ms: float = 0.0):
        """已有源图 → 建会话 → 重挂该重挂的层 → 出帧。新导入与底片条切换共用这一段。"""
        self._creative_original_dimensions = getattr(d, "_creative_original_dimensions", (d.src_w, d.src_h))
        restore_channel = p.get("channel", self._channel)
        restore_grade_scope = self._grade_scope
        shm = self._ensure_shm(d.w, d.h)
        t_a = monotonic_ns()
        self._people_prepare_open(d,p)
        pipe = self._attach_pipeline(CDH.original_proxy(d))      # 按引擎侧字段重放图层（见 _attach_pipeline）
        self._image_loaded = True
        optics_row = self._docs[self._doc_index]
        library_capture_decoded(optics_row, d)
        OPR.import_metadata(self,d,new=bool(optics_row.pop('_optics_new_import',False)))
        if strength is not None:
            self._fence_current_document()
            self._strength = strength
        t_b = monotonic_ns()
        # 切回一张调过的图时预计算产物在状态里带着：会话是新设备/新张量，不重挂
        # 就是“掩膜在这张图的旧会话里，屏幕读的是新会话”——与换设备那个坑同形。
        if self._precompute is not None:
            self._rehang_precompute(replayed_for="doc_switch" if switched else "load")
        elif self._channel:
            emit({"event": "engine_warn", "warn": "蒙版尚未恢复：保留编辑参数，暂不应用该范围的磨皮，不回退为全图"})
        effective_strength, effective_channel = self._retouch_render_args()
        FABRIC.sync(self)
        LM.sync(self); LGR.sync(self); MLR.sync(self); SBR.sync(self); OPR.sync(self); SKR.sync(self); LIPR.sync(self); BROWR.sync(self); NOSER.sync(self); EYER.sync(self); MOUTHR.sync(self); self._people_sync(); IDR.sync(self); ERR.sync(self); RCR.sync(self); SCR.sync(self); ETH.sync_current(self); PDH.sync_current(self); CGA.sync(self); SCLA.sync(self); CEA.sync(self); PCA.sync(self)
        self._people_render_open(pipe,lambda:CER.render_preview(self) if CER.active(self) else PGR.render_preview(self) if PGR.active(self) else SKR.render_proxy(self,lambda:pipe.render(effective_strength, channel=effective_channel, **self._params)))
        with self._wlock:
            seq, t_emit, slot = shm.write_frame(pipe.read_back(), presentation=self._frame_presentation(str(t0), (d.src_w,d.src_h), "original" if self._people_open_flags() else "edited"))
        t_c = monotonic_ns()
        row = self._docs[self._doc_index] if 0 <= self._doc_index < len(self._docs) else None
        if row is not None:
            row.update({"w": d.w, "h": d.h, "src_w": d.src_w, "src_h": d.src_h,
                        "opened": True, "state": self._capture_state()})
        self._load_id = str(t0)
        emit({"event": "image_ready", **d.meta(), "load_id": self._load_id, "device": str(pipe.device), **SKR.proxy_flags(self), **self._people_open_flags(),
              "strength": self._strength,
              # 底片条得知道现在这一格是哪一张、是不是切回来的（而不是新导入）：
              # UI 拿它把高亮位置对好，不靠“我自己记得点过第几格”。
              "session_index": self._doc_index, "doc": self._doc_path,
              "switched": bool(switched),
              # 逐段归因，不留“由减法得出的一坨”：验收口径①要的是「解码」与「初始化常驻张量」
              # 两个分开数。首次 attach 里含着 CUDA 上下文/内核模块的进程级 lazy init，
              # 不拆开来就会把它当成「每张图都要 150 ms」写进产品结论。
              "shm_ms": round((t_a - t0) / 1e6 - d.t_total_ms - device_prepare_ms, 2),
              "device_prepare_ms": round(device_prepare_ms, 2),
              "attach_ms": round((t_b - t_a) / 1e6, 2),
              "first_frame_ms": round((t_c - t_b) / 1e6, 2),
              # M1-3c：首帧里含一次与强度无关的滤波（产品档实测 ~4.5 ms）。不拆进单独字段，
              # first_frame_ms 就会被读成“每帧都得 4.5 ms”，而拖拽期实际只付混合那 0.1 ms。
              # 一次性成本与逐帧成本混在一起量就分不出谁是谁。
              "first_frame_filter_ms": round(float(pipe.last_filter_ms), 2),
              # M2-a：首帧那一笔里“分带”与“重组”各占多少。两者混在一个数里就看不出
              # 分层缓存有没有价值（分带贵、重组便宜）。
              "first_frame_bands_ms": round(float(pipe.last_bands_ms), 2),
              # 零推理换来的显存代价必须能看见，不能只报快了多少
              "bytes_filter": pipe.filter_resident_bytes(),
              "bytes_bands": pipe.bands_resident_bytes(),
              # 以下是**当前文档**的图层账单。第一次导入时它们必须是 0（那一层还没人动过），
              # 而切回一张画过笔的图时它们就是那几笔的真实占用——那时报 0 才是错。
              "bytes_light": pipe.light_resident_bytes(),
              "bytes_effect_recovery": pipe.effect_recovery_resident_bytes(), "bytes_manual_liquify": pipe.manual_liquify.resident_bytes(),
              "bytes_deform": pipe.deform_resident_bytes(),
              # 预热会话那张临时表不能让真会话继承（不然这里会多报 428 KB 而用户一张
              # 预设也没点）；同理，切回一张挂了表的图时这里就应当非 0。
              "bytes_lut": pipe.lut_resident_bytes(),
              "layers": self._layer_counts(),
              # 切回来的那一刻，宿主要按这一份重摆所有滑块（那些 *_done 快照已被清，
              # 而它们属于上一条命令而不是这张文档）
              "doc_state": self.doc_state(),
              # M3-b：定向层的四个数。宿主靠这一份快照摆滑块，不留它就只能把上一张图的
              # 肤色参数继续显示成“已调”（与 bytes_lut 同一条理由）。
              "grade_state": dict(dh=float(pipe.grade_params[0]), ds=float(pipe.grade_params[1]),
                                  dv=float(pipe.grade_params[2]), amount=float(pipe.grade_amount),
                                  lit=bool(pipe.has_grade()),
                                  bytes_grade=int(pipe.grade_resident_bytes())),
              # 只报滤波这一份：新导入时掩膜在本事件之后才挂上（precompute 跑在 image_ready 后面），
              # 这里附 bytes_face 恒为 0，反而会被读成"掩膜没常驻"。掩膜/关键点的字节数由
              # precompute_ready 报，那才是它们为真的那一刻（切回来的图也会重发那一条）。
              "import_ms": round((t_c - t0) / 1e6, 2),
              # RAW 秒开那一帧的账（没推过预览就是 None）：宿主与跑靶拿它分“看到画面”
              # 与“可以编辑”两个时刻，混成一个数就会把预览的 3 ms 报成导入的 3 ms
              "preview_ms": (self._preview_info or {}).get("ms"),
              "preview_size": ([self._preview_info["w"], self._preview_info["h"]]
                               if self._preview_info else None)})
        self._preview_info = None            # 一帧一次：下一条导入重新算，不沿用旧账
        emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
              "w": shm.w, "h": shm.h, "mode": "image", **self._people_open_flags()})
        self.emit_session_state()
        # 导入期预计算：产品上“导图就算一次”，但它是可选步——失败不许把导入本身拖成失败。
        # 它自己的 error 事件会单独发，报表里 backend/resident 一眼可验。
        # 判据是“这张图现在有没有关键点”，不是“是不是第一次开”：切回一张关键点已被
        # 作废（代理档变了）的图时，那一次推理得重新付，否则形变/通道两层都是空的。
        if p.get("precompute") and self._precompute is None:
            self.cmd_precompute({"backend": p.get("backend", "auto"),
                                 "model_dir": p.get("model_dir"),
                                 "channel": restore_channel})
            if self._precompute is not None and (restore_channel or restore_grade_scope == "skin"):
                if restore_grade_scope == "skin":
                    self._grade_scope = "skin"
                    self._rehang_grade_scope(replayed_for="project_reanalysis")
                # Reanalysis must publish the restored pixels, not leave the
                # first unmasked loading frame on screen with a masked status.
                emit(self._write_current_frame("precompute_restore"))
                self.emit_session_state()

    def _layer_counts(self) -> dict:
        """当前文档有哪几层。底片条那一格的“已调”徽章、UI 的状态栏、测试的断言
        全部只依这一份，不再各自拼一遍（拼三份就会漂三份）。"""
        return self._state_edits(self._capture_state())

    def doc_state(self) -> dict:
        """宿主摆滑块要用的那一份完整文档状态（随 image_ready 一起发）。

        为什么不能只靠图层计数与 grade_state：切回一张调过的图时，宿主手里那些
        `*_done` 快照已经被清掉了（它们说的是上一条命令，不是这一张文档），而滑块
        的位置必须来自引擎。缺了 lut_amount / deform 那一组数 / 修容那两个参数，
        UI 就只能"画面已经调好了但滑块显示 0"——那是双向错配的新一格。
        """
        from .ops.geometry import geometry_state as geo_state

        # 裁剪/旋转独立一层，不塞在 exposure 的字面里：上一版把 crop 嵌进了
        # exposure 那个字典（缩进也一样），宿主按 doc_state["crop"] 取就永远取不到，
        # 而这份错在 JSON 里看起来完全自洽。量程也不在这里写字面量：ops.geometry
        # 那份是唯一出处，UI 自己抄的 [-180,180] 与引擎实际拒的值迟早分叉。
        crop = geo_state(list(self._crop_rect), float(self._crop_rotation))
        crop["lit"] = not crop["neutral"]
        # 剪后尺寸两个数：crop_out 是代理档上的（预览那一层就是它），out_full 是
        # 导出会写的真实像素数。它们原来只在 frame 事件里带（宿主那份 doc_report
        # 只从 image_ready/session_state/history_state 来），于是“裁完看一眼工具栏”
        # 永远是空的——UI 写了读这两格的代码，却没有一条路能把数送到。
        if self._vram is not None:
            from .ops.geometry import out_size as _gsz
            crop["crop_out"] = list(_gsz(int(self._vram.w), int(self._vram.h),
                                         tuple(self._crop_rect),
                                         float(self._crop_rotation)))
            row = self._docs[self._doc_index] if 0 <= self._doc_index < len(self._docs) else None
            if row and row.get("src_w") and row.get("src_h"):
                crop["out_full"] = list(_gsz(int(row["src_w"]), int(row["src_h"]),
                                             tuple(self._crop_rect),
                                             float(self._crop_rotation)))
        return {"fringe_repair":self._fringe_status(), "document_id": self._load_id, "source_uid": CDH.source_uid(self), "photo_detail": {**PDS.status(self._photo_detail),"available":PDH.available()}, "photo_grain": PGA.report(self), "colour_grading": CGA.report(self), "primary_calibration": PCA.report(self), "selective_colour": SCLA.report(self), "colour_editor": CEA.report(self), "extended_tone": {**ETS.status(self._extended_tone), "available": (Path(__file__).parent/"bin/liblrt_extended_tone.so").is_file()}, "fabric": FABRIC.status(self), "local_masks": LM.state(self), "effect_recovery": ERR.report(self), "manual_liquify": MLR.report(self), "studio_background": SBR.report(self), "id_background": IDR.report(self), "optics": OPR.report(self), "sky_replacement": SKR.report(self), "lip_makeup": LIPR.report(self), "brow_shape": BROWR.report(self), "nose_shape": NOSER.report(self), "eye_shape": EYER.report(self), "mouth_shape": MOUTHR.report(self), "reference_color": RCR.report(self), "semantic_colour": SCR.report(self), **self._body_report(),
                "canvas_guides": CGH.report(self),
                "strength": float(self._strength), "params": dict(self._params),
                "channel": self._channel,
                "history": self._history_report(),
                "light": dict(self._light),
                "counts": {"repair": len(self._repair_ops), "light": len(self._light_ops),
                           "light_redo": len(self._light_redo), "repair_redo": len(self._redo_ops)},
                "deform": {"amounts": dict(self._deform["amounts"]),
                           "scope": "person" if self._override_for(self._face_box) else "all",
                           **self._layered_deform_state(),
                           "built": bool(self._deform["built"]),
                           # 重开工程/迁会话后“有这一层而关键点还没回来”（CORE-001）：
                           # UI 拿它把面板标成“待重新分析”，而不是把滑块弹回 0
                           "defer": bool(self._deform_defer)},
                "lut": {"lit": self._lut is not None, "amount": float(self._lut_amount),
                        "preset": self._lut_preset, "asset_id": getattr(self._lut, "asset_id", None)},
                "grade": {"dh": float(self._grade[0]), "ds": float(self._grade[1]),
                          "dv": float(self._grade[2]), "amount": float(self._grade[3]),
                          "lit": self._grade != (0.0, 0.0, 0.0, 1.0),
                          # COLOR-004：作用域与“区域真盖了多少格”。UI 的作用域选择框与
                          # “被拒/已生效”的文案必须从这里取：换图、重开工程、撤销都会改它，
                          # 而 UI 自己记一份就是在替引擎说谎。mask_px 从宿主字段算（那才是
                          # 可重建一份区域的全部信息），不拿会话里那份张量当唯一证人。
                          "scope": str(self._grade_scope), "scopes": list(GRADE_SCOPES),
                          "mask_px": 0 if self._grade_mask is None
                          else int((self._grade_mask > 0).sum())},
                # PORTRAIT-009：三个子功能的值、这一层真点火了没有、以及"没点火时那一句
                # 原因"。UI 的开关与提示必须从这里取：自己记一份就会在换图/重开工程/换人选
                # 之后替引擎说谎（这一层的 reason 有五种来源，都不是前端能推出来的）
                "enhance": {**ENH.TEETH.capability(), **ENH.RED_EYE.capability(), **ENH.PURIFY.capability(), "amounts": dict(self._enhance["amounts"]),
                            "subs": list(ENH.EFFECT_KEYS),
                            "limit": [0.0, float(ENH.AMOUNT_LIMIT)],
                            "lit": bool(self._vram.has_enhance()) if self._vram else False,
                            "built": bool(self._enhance["built"]),
                            "defer": bool(self._enhance_defer),
                            "box": (list(self._enhance["box"]) if self._enhance.get("box")
                                    else None),
                            "facial_wrinkles": {k: dict((self._vram.enhance_facts if self._vram else {}).get(k) or {}) for k in WSTATE.KEYS},
                            "gated_px": {k: int(((self._vram.enhance_facts if self._vram
                                                  else {}) or {}).get(k, {})
                                                 .get("gated_px", 0)) for k in ENH.EFFECT_KEYS},
                            "reason": {k: ((self._vram.enhance_facts if self._vram else {})
                                           or {}).get(k, {}).get("reason")
                                       for k in ENH.EFFECT_KEYS}},
                "exposure": {"ev": float(self._exposure[0]),
                             "temperature_shift": float(self._exposure[1]),
                             "tint_shift": float(self._exposure[2]),
                             "contrast": float(self._exposure[3]),
                             "highlights": float(self._exposure[4]),
                             "shadows": float(self._exposure[5]),
                             "saturation": float(self._exposure[6]),
                             "reference_k": self._exposure_ref_k,
                             "options": WB.check_options(self._wb_options),
                             "lit": self._exposure != (0.0,) * 7 or WB.has_picks(self._wb_options)},
                # 八色 HSL：数组顺序与 ops/hsl.py 的 BAND_NAMES 一一对应；量程也
                # 从引擎报（UI 不抄一份数）。
                "curves": CURVES.check_curves(self._curves), "levels": self._levels,
                "hsl": {"bands": [float(v) for v in self._hsl],
                        "names": list(BAND_NAMES),
                        "centers": [float(v) for v in BAND_CENTERS],
                        "limits": {"hue": float(HSL_HUE_LIMIT),
                                   "sat": float(HSL_SAT_LIMIT),
                                   "lum": float(HSL_LUM_LIMIT)},
                        "lit": self._hsl != (0.0,) * 24},
                # 多人图里“现在在改哪一张”（PORTRAIT-003）。chip 数几个、能不能放行，
                # 全从这一格取：名单是分析结果里算出来的，前端数不来也不许猜。
                "face": self._face_state(), "people": self._people_report(),
                "crop": crop}

    def _state_edits(self, st: dict) -> dict:
        """一份状态（live 抄出来的或底片条格子里存着的）里有哪些层。"""
        return {"fringe_repair":FRS.active(FRS.from_state(st)), "photo_detail": PDS.active(st.get("_photo_detail")), "photo_grain": PGS.active(PGS.from_state(st)), "colour_grading": CGS.active(CGS.from_state(st)), "primary_calibration": PCS.active(PCS.from_state(st)), "selective_colour": SCSL.active(SCSL.from_state(st)), "colour_editor": CES.active(CES.from_state(st)), "extended_tone": ETS.active(st.get("_extended_tone")), "local_masks": len((st.get("_local_masks") or LM.empty())["recipe"]["objects"]),
                "local_grade_layers": len(LG.check(st.get("_local_grade_layers"))["layers"]),
                "effect_recovery": len(ERS.check(st.get("_effect_recovery"))["targets"]),
                "manual_liquify": len(MLS.check(st.get("_manual_liquify"))["strokes"]),
                "optics": OPS.active(st.get("_optics")),
                "sky_replacement": SKS.check(st.get("_sky_replacement"))["enabled"],
                "studio_background": SBS.active(st.get("_studio_background")), "id_background": IDS.active(st.get("_id_background")), "lip_makeup": LIPS.active(st.get("_lip_makeup")), "brow_shape": BROWS.active(st.get("_brow_shape")), "nose_shape": NOSES.active(st.get("_nose_shape")), "eye_shape": EYES.active(st.get("_eye_shape")), "mouth_shape": MOUTHS.active(st.get("_mouth_shape")),
                "fabric": bool(st.get("_fabric_amount", 0.0)), "repair": len(st["_repair_ops"]), "light": len(st["_light_ops"]),
                "deform": any(abs(float(v)) > 0.0 for v in st["_deform"]["amounts"].values()),
                "lut": st["_lut"] is not None, "lut_preset": st["_lut_preset"],
                "grade": st["_grade"] != (0.0, 0.0, 0.0, 1.0),
                "enhance": WSTATE.active_enhance(st["_enhance"]["amounts"] or {}),
                # 旧工程档里可能还没有这一格：缺键按“没调过”算，不拿 KeyError 把
                # 整条底片条打成红。
                "hsl": any(float(v) != 0.0 for v in (st.get("_hsl") or ())),
                "curves": not CURVES.is_identity(st.get("_curves")), "levels": not LEVELS.is_identity(st.get("_levels")),
                "channel": st["_channel"]}

    # ------------------------------------------------------------ M5-a 底片条
    SESSION_KEYS = {"cmd", "action", "dir", "paths", "index", "limit", "edge",
                    "quality", "thumbs", "query", "request_id", "session_id", "selected_path", "document_id"}
    # 每解这么多张让一次 GIL：缩略图解码是纯 CPU 活，而帧通路每秒要 60 次调度。
    # 该不该让、让多少不是拍出来的，是 m5-filmstrip-bench 那两臂量出来的。
    THUMB_BATCH = 4
    THUMB_SLEEP_MS = 2.0

    def _doc_row_event(self, i: int, d: dict) -> dict:
        """底片条一格上报的形状。当前那一格用 live 字段，不用格子里存的快照
        （快照停在上一次开会话时，刚刚画上去的那一笔还不在里面）——徽章慢一帧就是假事实。

        `preview`/`format` 不能在这里丢：RAW 那一格画的是相机内嵌预览，不是我们渲的
        那一帧。`thumb_ready` 里带了这两个字段，可宿主重连与重扫之后拿的是
        `session_state`——这里丢一次，底片条就分不出“jpg 的真图”与“DNG 的相机预览”，
        用户以为第一格就是母档质量，调完发现不是，那比不标更坏。"""
        st = self._capture_state() if (i == self._doc_index and self._image_loaded) else d["state"]
        th = d["thumb"]
        row = {"index": i, "path": d["path"], "name": d["name"],
                "bytes_on_disk": d["bytes_on_disk"], "w": d["w"], "h": d["h"],
                "src_w": d["src_w"], "src_h": d["src_h"],
                "loaded": (i == self._doc_index and self._image_loaded),
                "opened": bool(d["opened"]),
                "edits": self._state_edits(st),
                # 项目层的三个字段随底片条上报：状态徽章（已标/回收站）与多选批量
                # 都要在格子上直接可读，否则 UI 只能自己再拼一份工程状态——那就是
                # doc_state 里 crop 被塞进 exposure 那一类错：两边各自自洽
                "tags": list(d.get("tags") or []), "label": d.get("label"),
                "trashed": bool(d.get("trashed")),
                "hashed": bool(d.get("fingerprint")),
                "thumb": None if th is None else {"w": th["w"], "h": th["h"],
                                                   "bytes": th["bytes"], "quality": th["quality"],
                                                   "preview": bool(th.get("preview")),
                                                   "format": th.get("format")},
                "thumb_error": d["thumb_error"],
                # 挑图那一格（PICK-001）。徽章只能读引擎这份：前端自己按缩略图亮度判断
                # 「这张糊不糊」就是又造一个不可复算的出处
                "pick": d.get("pick"), "pick_error": d.get("pick_error")}
        from .virtual_copy_host import IDENTITY_KEYS
        row.update({k:d[k] for k in IDENTITY_KEYS})
        return LQ.enrich_row(self, i, d, row, st)



    @property
    def _preset_last(self): return self._preset_controller().last

    @_preset_last.setter
    def _preset_last(self, value): self._preset_controller().last = value

    def _preset_last_applied(self): return self._preset_controller().last_applied()

    def _preset_state(self): return self._preset_controller().state()

    def _sync_state(self) -> dict:
        return self._batch_controller().summary()

    def emit_session_state(self, **extra) -> None:
        rows = [self._doc_row_event(i, d) for i, d in enumerate(self._docs)]
        emit({"event": "session_state", "index": self._doc_index, "count": len(self._docs),
              "current": self._doc_path,
              # 当前文档的完整状态（live 取的，不是格子里存的快照）。宿主拿它重摆滑块，
              # 也拿它做"切走再切回来，数字对不对得上"的基线——只有 image_ready 里那份
              # 的话，基线就停在开图那一刻，之后的每一次调参都不在里面。
              "doc_state": (self.doc_state()
                            if (self._image_loaded and self._vram is not None) else None),
              "thumbs_running": bool(self._thumbs is not None and self._thumbs.is_alive()),
              "picks_running": bool(self._picks is not None and self._picks.is_alive()),
              "project": self._project_state(),
              # 预设清单与批量同步台账：UI 的下拉项与“撤销同步”按钮只能读引擎报的这两份
              #（前端自己扫目录、自己记 batch_id 就是两个会漂的地方）。
              "presets": self._preset_state(), "sync": self._sync_state(),
              "docs": rows, "library_query": LQ.query_state(self, rows), **extra})

    def _rows_from(self, paths: list, origins=None) -> list:
        from .virtual_copy_session import rows_from
        return rows_from(self, paths, origins)

    def _start_thumbs(self, indices: list, edge, quality) -> bool:
        try:
            edge = S.valid_edge(edge)
            q = int(quality)
            if not S.MIN_THUMB_QUALITY <= q <= 100:
                raise ValueError(f"quality={q} 越界（允许 {S.MIN_THUMB_QUALITY}~100）")
        except (ValueError, TypeError) as e:
            emit({"event": "error", "error": f"缩略图参数非法：{e}"})
            return False
        # Validate first: invalid requests must not depend on worker timing.
        if self._thumbs is not None and self._thumbs.is_alive():
            emit({"event": "error", "error": "缩略图任务已在跑：先 session action=stop_thumbs"})
            return False
        self._thumb_stop.clear()
        self._thumb_args = (list(indices), edge, q)
        self._thumbs = threading.Thread(target=self._thumb_loop, daemon=True)
        self._thumbs.start()
        return True

    def _thumb_loop(self):
        """逐张解缩略图并发 thumb_ready。

        归属看 **path 不看 index**：列表可能在半路上被第二次 scan 换掉，那时按 index
        发出去会把上一轮的图放进不相干的那一格——而且事件里任何数字看起来都正常。
        格子里有没有图也要在写之前再看一眼（已有就跳过，不重解）。
        """
        idxs, edge, quality = self._thumb_args
        t0 = monotonic_ns()
        n = failed = dropped = 0
        channel_bytes = 0
        thumb_ms_sum = 0.0
        for j, i in enumerate(idxs):
            if self._thumb_stop.is_set():
                dropped += len(idxs) - j
                break
            with self._doclock:
                path = self._docs[i]["path"] if 0 <= i < len(self._docs) else None
                need = path is not None and self._docs[i]["thumb"] is None \
                    and self._docs[i]["thumb_error"] is None
            if not need:
                dropped += 1
                continue
            try:
                info = S.make_thumb(path, edge=edge, quality=quality)
            except Exception as e:                # 一张解不开只塔自己那一格，不带倒整批
                failed += 1
                with self._doclock:
                    if 0 <= i < len(self._docs) and self._docs[i]["path"] == path:
                        self._docs[i]["thumb_error"] = f"{type(e).__name__}: {e}"
                emit({"event": "thumb_failed", "index": i, "path": path,
                      "error": f"{type(e).__name__}: {e}"})
                continue
            b64 = info.pop("jpeg_b64")
            channel_bytes += len(b64)
            n += 1
            thumb_ms_sum += info["total_ms"]
            with self._doclock:
                if 0 <= i < len(self._docs) and self._docs[i]["path"] == path:
                    self._docs[i]["thumb"] = info
            emit({"event": "thumb_ready", "index": i, "path": path, **info, "jpeg_b64": b64})
            if (j + 1) % self.THUMB_BATCH == 0 and self.THUMB_SLEEP_MS > 0:
                time.sleep(self.THUMB_SLEEP_MS / 1000.0)
        emit({"event": "thumbs_done", "count": n, "failed": failed, "dropped": dropped,
              "edge": edge, "quality": quality,
              "decode_ms_sum": round(thumb_ms_sum, 2),
              "channel_kb": round(channel_bytes / 1024.0, 1),
              "stopped": bool(self._thumb_stop.is_set()),
              "total_ms": round((monotonic_ns() - t0) / 1e6, 1)})
        self.emit_session_state()

    def cmd_session(self, p: dict):
        """底片条：扫目录、加图、切文档、看状态、管缩略图任务。"""
        unknown = set(p) - self.SESSION_KEYS
        if unknown:
            emit({"event": "error", "error": f"session 收到不认识的参数：{sorted(unknown)}"})
            return
        action = p.get("action", "state")
        if action == "query":
            LQ.set_query(self, p)
            self.emit_session_state(view_only=True)
            return
        if action == "scan":
            if "dir" not in p:
                emit({"event": "error", "error": "session scan 需要 dir"})
                return
            try:
                limit = int(p.get("limit", S.MAX_DOCS))
                if not 1 <= limit <= S.MAX_DOCS:
                    raise ValueError(f"limit={limit} 越界（允许 1~{S.MAX_DOCS}）")
                got = S.scan_dir(str(p["dir"]), limit=limit)
            except (ValueError, TypeError, OSError) as e:
                emit({"event": "error", "error": f"scan 失败({type(e).__name__}): {e}"})
                return
            if self._thumbs is not None and self._thumbs.is_alive():
                self._thumb_stop.set()      # 旧任务下一轮会自己按 path 对不上而退出
            self._remember_current()
            from .export_destination_import import origin
            rows = self._rows_from(got["files"], {path:origin(path, got["dir"], kind="directory") for path in got["files"]})
            emit({"event": "session_scan", "dir": got["dir"], "found": len(got["files"]),
                  "rows": len(rows), "truncated": got["truncated"], "skipped": got["skipped"],
                  "limit": limit, "scan_ms": got["scan_ms"],
                  "current": self._doc_path, "current_index": self._doc_index})
            self.emit_session_state()
            if p.get("thumbs", True):
                self._start_thumbs([i for i, d in enumerate(rows) if d["thumb"] is None],
                                   p.get("edge", S.EDGE), p.get("quality", S.THUMB_QUALITY))
            return
        if action == "add":
            paths = p.get("paths")
            if not isinstance(paths, list) or not paths:
                emit({"event": "error", "error": "session add 需要 paths（非空路径列表）"})
                return
            if any((not isinstance(x, str) or not x) for x in paths):
                emit({"event": "error", "error": "session add 的 paths 必须是非空字符串列表"})
                return
            # 先验存在再提交（与所有 cmd_* 同一条铁律）：收一条不存在的路径进底片条，
            # 代价要拖到缩略图线程或用户点上去那一刻才报，而那时已经看不出来是哪一步错了。
            from .export_destination_import import expand
            try:
                paths, origins = expand(paths, S.IMAGE_EXTS, S.MAX_DOCS)
            except (ValueError, OSError) as error:
                emit({"event":"error", "error":str(error)}); return
            self._remember_current()
            before = {d["path"] for d in self._docs}
            rows = self._rows_from(list(self._doc_paths()) + [str(x) for x in paths], origins)
            added = [d["path"] for d in rows if d["path"] not in before]
            emit({"event": "session_add", "requested": len(paths), "added": len(added),
                  "duplicated": len(paths) - len(added), "rows": len(rows)})
            self.emit_session_state()
            if p.get("thumbs", True):
                self._start_thumbs([i for i, d in enumerate(rows) if d["path"] in set(added)],
                                   p.get("edge", S.EDGE), p.get("quality", S.THUMB_QUALITY))
            return
        if action == "select":
            try:
                idx = int(p["index"])
            except (KeyError, TypeError, ValueError):
                emit({"event": "error", "error": "session select 需要 index（整数）"})
                return
            if not 0 <= idx < len(self._docs):
                emit({"event": "error", "error": f"index={idx} 不在底片条里（共 {len(self._docs)} 格）"})
                return
            if ((p.get("session_id") is not None and p["session_id"] != LQ.session_id(self))
                    or (p.get("selected_path") is not None and p["selected_path"] != self._docs[idx]["path"])
                    or (p.get("document_id") is not None and p["document_id"] != self._docs[idx]["document_id"])):
                emit({"event": "error", "error": "图库身份已变化，请刷新后重试选择"})
                return
            if idx == self._doc_index and self._image_loaded:
                # 重复点当前那一格不开新会话：白付一次解码与重建，而且会把未存快照的
                # live 状态当“新文档默认值”重装一轮（那就是静默丢工）
                self.emit_session_state(noop=True)
                return
            row = self._docs[idx]
            cmd = {"path": row["path"], "document_id": row["document_id"]}
            if self._proxy_budget:
                cmd["max_px"] = int(self._proxy_budget)
            # 切文档走的就是 load_image 那一条路，不写第二份：守卫（跑靶/导出互斥）、
            # 尺寸比对、预计算重挂、事件形状全部同源
            self.cmd_load_image(cmd)
            return
        if action == "thumbs":
            return self._start_thumbs([int(x) for x in p.get("indices", [])] if p.get("indices")
                                      else list(range(len(self._docs))),
                                      p.get("edge", S.EDGE), p.get("quality", S.THUMB_QUALITY))
        if action == "stop_thumbs":
            self._thumb_stop.set()
            self.emit_session_state(stopped=True)
            return
        if action == "state":
            self.emit_session_state()
            return
        emit({"event": "error", "error": f"未知 session action: {action}"
              f"（可用：scan/add/select/thumbs/stop_thumbs/state）"})

    def _doc_paths(self):
        return [d["path"] for d in self._docs]

    # ------------------------------------------------------------ 挑图建议（LNX-PICK-001）
    PICK_ACTIONS = ("analyze", "stop", "state")
    PICK_KEYS = {"cmd", "action", "indices", "paths", "edge", "model_dir", "force",
                 "duplicate", "blur", "exposure", "eyes"}
    # 度量时的解码尺度：像素类度量自己在 picks 层再降到长边 160，这一档决定的是
    # 「FaceMesh 能看到多大的眼」与「要不要为一原图付全额解码」。160 太小（眼睑几个
    # 像素，几何量全是噪声），全额解码太慢（挑图是一次过几百张的后台活）。
    PICK_EDGE = 512
    PICK_MIN_EDGE = 160
    PICK_MAX_EDGE = 1024
    PICK_BATCH = 3
    PICK_SLEEP_MS = 2.0
    # 四组敏感度：档位名 → 那张表。名单只有一个出处（picks 层），ready 里报出去的
    # 与这里校验的是同一份，所以「可用名单」这句话不会是假的。
    PICK_SENS_TABLE = {"duplicate": PK.DUPLICATE_SENSITIVITY, "blur": PK.BLUR_SENSITIVITY,
                       "exposure": PK.EXPOSURE_SENSITIVITY, "eyes": PK.EYE_SENSITIVITY}

    def _pick_sens(self, p: dict) -> dict | None:
        out: dict = {}
        for name, table in self.PICK_SENS_TABLE.items():
            got = p.get(name, "standard")
            if got not in table:
                emit({"event": "error", "error": f"pick 的 {name} 档位 {got!r} 不在名单里"
                      f"（可用：{sorted(table)}，名单在 ready 的 pick_sensitivities 里）"})
                return None
            out[name] = got
        return out

    def _pick_targets(self, p: dict) -> list | None:
        """要分析哪几格：indices / paths 二选一，都不给就是整条底片条。

        默认**跳过已分析过的格子**（与缩略图同一口径：重跑一次不该把几百毫秒再付一遍），
        `force=True` 才全部重算——判据指纹换了的时候用户就需要它（数值不可比）。
        """
        want_idx, want_paths = p.get("indices"), p.get("paths")
        if want_idx is not None and want_paths is not None:
            emit({"event": "error", "error": "pick 的 indices 与 paths 只能给一个"
                                             "（它们是不同的东西：位置与身份）"})
            return None
        with self._doclock:
            n = len(self._docs)
            rows = list(self._docs)
        idxs: list = []
        if want_idx is not None:
            if not isinstance(want_idx, list) or not want_idx:
                emit({"event": "error", "error": "pick 的 indices 要是非空整数列表"})
                return None
            for x in want_idx:
                try:
                    i = int(x)
                except (TypeError, ValueError):
                    emit({"event": "error", "error": f"pick 的 index 不是整数：{x!r}"})
                    return None
                if not 0 <= i < n:
                    emit({"event": "error", "error": f"index={i} 不在底片条里（共 {n} 格）"})
                    return None
                idxs.append(i)
        elif want_paths is not None:
            if not isinstance(want_paths, list) or not want_paths:
                emit({"event": "error", "error": "pick 的 paths 要是非空路径列表"})
                return None
            by = {d["path"]: i for i, d in enumerate(rows)}
            for x in want_paths:
                ap = os.path.abspath(str(x))
                if ap not in by:
                    emit({"event": "error", "error": f"底片条里没有这一张：{x}"
                          f"（先 session add 再挑图，两侧名单必须同一份）"})
                    return None
                idxs.append(by[ap])
        else:
            idxs = list(range(n))
        out: list = []
        seen: set = set()
        skipped = 0
        for i in idxs:
            if i in seen:
                continue
            seen.add(i)
            if not p.get("force", False) and rows[i].get("pick") is not None:
                skipped += 1
                continue
            out.append(i)
        if skipped:
            emit({"event": "engine_warn", "warn": f"pick：{skipped} 格已有建议，本次跳过"
                                                  "（要重算给 force=true；判据指纹变了也建议重算，"
                                                  "不同版算法的数值不可比）"})
        return out

    def _start_picks(self, idxs: list, edge: int, model_dir, sens: dict) -> bool:
        if self._picks is not None and self._picks.is_alive():
            emit({"event": "error", "error": "挑图任务已在跑：先 pick action=stop"})
            return False
        if not idxs:
            emit({"event": "pick_done", "count": 0, "failed": 0, "groups": [],
                  "reason": "没有要分析的格子（都已分析过或被筛掉）",
                  "fingerprint": PK.fingerprint(), "sensitivities": sens})
            return False
        self._pick_stop.clear()
        self._pick_args = (list(idxs), int(edge), model_dir, dict(sens))
        self._picks = threading.Thread(target=self._pick_loop, daemon=True)
        self._picks.start()
        return True

    def _pick_measure_one(self, path: str, edge: int, fn, eyes_error):
        """一张图的全部读数。只读文件，一个字节都不写回去（原片只读）。"""
        from .decode import clamp_budget, load_rgb

        m = PK.Measures(path=str(path))
        t0 = monotonic_ns()
        d = load_rgb(path, clamp_budget(int(edge) * int(edge)), allow_preview=True)
        t1 = monotonic_ns()
        rgb = d.rgb
        m.decode_size = (int(rgb.shape[1]), int(rgb.shape[0]))
        # RAW 走相机内嵌预览时必须说出来：那张预览是相机自己锐化/降噪过的，
        # 「糊」的读数不再属于母档（与底片条同一个开关、同一个理由）
        m.decoded_from = ("camera_preview"
                          if (d.raw or {}).get("source") == "libraw_preview" else "pixels")
        cl = PK.clarity(rgb)
        m.sharpness, m.ratio, m.contrast = cl["lapvar"], cl["ratio"], cl["contrast"]
        m.under, m.over = PK.exposure_shares(rgb)
        m.dhash = PK.dhash64(rgb)
        t2 = monotonic_ns()
        if fn is None:
            m.eye_note = (f"眼睑那一档没量：FaceMesh 后端不可用（{eyes_error}）——"
                          "这一格不写「睁眼」，也不写「闭眼」")
        else:
            try:
                pc = fn(rgb)
            except Exception as e:
                m.eye_note = (f"眼睑那一档没量：FaceMesh 推理失败({type(e).__name__}): {e}"
                              "——这一格不写「睁眼」，也不写「闭眼」")
            else:
                pool = list(pc.all_landmarks or ([pc.landmarks] if pc.landmarks is not None else []))
                m.faces = len(pool)
                vals = [PK.eye_openness(lm, image_size=m.decode_size) for lm in pool]
                vals = [v for v in vals if v is not None]
                # 多人图取**最小**的那一张脸的那一只眼：任何一个人闭眼都值得复核，
                # 取均值会把「半个人闭眼」冲淡成"没问题"
                m.eye_open = min(vals) if vals else None
                if m.eye_open is None:
                    m.eye_note = (f"画面里探到 {m.faces} 张脸，但没有一份关键点够 478 点契约"
                                  "——这一格不写「睁眼」，也不写「闭眼」")
        t3 = monotonic_ns()
        m.ms = {"decode_ms": (t1 - t0) / 1e6, "pixel_ms": (t2 - t1) / 1e6,
                "face_ms": (t3 - t2) / 1e6}
        return m

    def _pick_write(self, path: str, **fields) -> int:
        """按 path 认格子再写（与缩略图同一条铁律：列表可能在半路上被换掉）。"""
        with self._doclock:
            for i, d in enumerate(self._docs):
                if d["path"] == path:
                    for k, v in fields.items():
                        d[k] = v
                    return i
        return -1

    def _pick_loop(self):
        """两遍：先逐张量读数（能发进度），再一次成组、折建议（分组要看到全部哈希）。

        一遍做完不行：近似组是全体哈希上的关系闭包，第 3 张的「组内第几名」要等第 200 张
        量完才知道。
        """
        from statistics import median

        idxs, edge, model_dir, sens = self._pick_args
        t0 = monotonic_ns()
        from . import face as face_mod
        fn = None
        eyes_error = None
        try:
            fn = face_mod.build("mediapipe", model_dir)
        except Exception as e:            # 后端/模型不在：像素那三档照量，眼睑如实报 unavailable
            eyes_error = f"{type(e).__name__}: {e}"
            emit({"event": "engine_warn", "warn": f"挑图：眼睑那一档不可用（{eyes_error}）。"
                                                  "清晰度/曝光/近似组仍然量，缺的那一格会显式标"
                                                  "「没量到」，不会退成「睁眼」"})
        order: list = []
        measured: dict = {}
        failed = 0
        for j, i in enumerate(idxs):
            if self._pick_stop.is_set():
                break
            with self._doclock:
                path = self._docs[i]["path"] if 0 <= i < len(self._docs) else None
            if path is None:
                continue
            try:
                m = self._pick_measure_one(path, edge, fn, eyes_error)
            except Exception as e:                # 一张解不开只坏自己那一格，不带到倒整批
                failed += 1
                self._pick_write(path, pick_error=f"{type(e).__name__}: {e}", pick=None)
                emit({"event": "pick_failed", "index": i, "path": path,
                      "error": f"{type(e).__name__}: {e}"})
                continue
            measured[path] = m
            order.append(path)
            emit({"event": "pick_progress", "index": i, "path": path,
                  "done": len(order), "total": len(idxs), "measures": m.for_json()})
            if (j + 1) % self.PICK_BATCH == 0 and self.PICK_SLEEP_MS > 0:
                time.sleep(self.PICK_SLEEP_MS / 1000.0)
        t_meas = monotonic_ns()
        # 分组池 = 本次量到的 + 本会话此前已经量过的那些格的哈希（存在 row["pick"] 里）。
        # 少了后半截就会出这种错：重跑一张，那张的"组内 3 张"变成"组内 1 张"，徽章自己在动。
        pool: dict = {p: {"dhash": measured[p].dhash, "ratio": measured[p].ratio,
                          "under": measured[p].under, "over": measured[p].over}
                      for p in order}
        with self._doclock:
            stored = [(d["path"], d.get("pick")) for d in self._docs]
        reused = 0
        for p, pk in stored:
            if p in pool or not pk:
                continue
            mm = pk.get("measures") or {}
            try:
                h = int(str(mm.get("dhash")), 16)
            except (TypeError, ValueError):
                continue          # 旧版算法没写这一格：不参与分组，不猜
            pool[p] = {"dhash": h, "ratio": float(mm.get("clarity_ratio") or 0.0),
                       "under": float(mm.get("under") or 0.0),
                       "over": float(mm.get("over") or 0.0)}
            reused += 1
        items = [(p, v["dhash"]) for p, v in sorted(pool.items())]
        groups = PK.group_duplicates(items, PK.DUPLICATE_SENSITIVITY[sens["duplicate"]])
        # 组内排名的依据：**相对自身对比度**（对整体曝光不敏感那一格），并列时看裁切占比，
        # 最后按路径稳定收尾——「本组最优」是一个可复算的排序结果，不是印象分
        info: dict = {}
        for g in groups:
            members = sorted([p for p in g if p in pool],
                             key=lambda p: (-pool[p]["ratio"],
                                            pool[p]["under"] + pool[p]["over"], p))
            for r, p in enumerate(members):
                others = [q for q in members if q != p]
                bits = min(PK.hamming(pool[p]["dhash"], pool[q]["dhash"])
                           for q in others) if others else None
                info[p] = {"members": members, "rank": r, "bits": bits}
        # 批内相对线用的是**池**的中位数（对比对象应当是同批全部，而不是只这次跑的那几张）；
        # 沿用旧哈希的那些格没有可读对比度那一格，但它们当初能进池就说明不是空白图
        ratios = [v["ratio"] for v in pool.values() if v["ratio"] > 0.0]
        ratios += [measured[p].ratio for p in order if measured[p].contrast >= PK.CONTRAST_FLOOR]
        med_ratio = float(median(ratios)) if ratios else 0.0
        fp = PK.fingerprint()
        emitted = 0
        for p in order:
            if self._pick_stop.is_set():
                break
            gi = info.get(p)
            m = measured[p]
            with self._doclock:
                row = next((d for d in self._docs if d["path"] == p), None)
            marked = bool(row is not None and ((row.get("tags") or []) or row.get("label")
                                               or row.get("trashed")))
            sug = PK.suggest(m, group=(gi["members"] if gi else [p]),
                             is_leader=bool(gi and gi["rank"] == 0),
                             rank_in_group=(gi["rank"] if gi else 0),
                             dup_bits=(gi["bits"] if gi else None),
                             dup=sens["duplicate"], blur=sens["blur"],
                             exposure=sens["exposure"], eyes=sens["eyes"],
                             batch_median_ratio=med_ratio,
                             group_scope={"analyzed": len(order), "pooled": len(pool)},
                             user_marked=marked)
            sug["fingerprint"] = fp
            sug["edge"] = int(edge)
            sug["batch_median_ratio"] = round(med_ratio, 4)
            sug["group_leader"] = (gi["members"][0] if gi else None)
            sug["decoded_from"] = m.decoded_from
            sug["analyzed_at_ns"] = int(monotonic_ns())
            idx = self._pick_write(p, pick=sug, pick_error=None)
            emit({"event": "pick_item", "index": idx, **sug})
            emitted += 1
        emit({"event": "pick_done", "count": emitted, "measured": len(order), "failed": failed,
              "pooled": len(pool), "reused_hashes": reused,
              "stopped": bool(self._pick_stop.is_set()),
              # 组只报「像」这一件事：成员、组内最优那一张、以及「这是关系闭包不是等价类」
              # 的那句 notes（在每条建议里）。这里绝不出现 delete/建议删除任何一张的说法。
              "groups": [{"size": len(g), "leader": (info[g[0]]["members"][0]
                                                     if g and g[0] in info else
                                                     (g[0] if g else None)),
                          "members": g} for g in groups],
              "sensitivities": sens, "thresholds": PK.thresholds_for_json(),
              "schema": PK.SCHEMA, "algo": PK.ALGO_VERSION, "fingerprint": fp,
              "edge": int(edge), "batch_median_ratio": round(med_ratio, 4),
              "eyes_backend": (fn.name if fn is not None else None),
              "eyes_error": eyes_error,
              "measure_ms": round((t_meas - t0) / 1e6, 1),
              "total_ms": round((monotonic_ns() - t0) / 1e6, 1)})
        self.emit_session_state()

    def cmd_pick(self, p: dict):
        """挑图建议（LNX-PICK-001）：本地确定性度量，可解释、可覆盖、**不自动删除**。

        冻结件的 then 有三句，这里一一对上：建议可覆盖（`overridable=True`，且人工标签
        在场时 `overridden_by_user=True`，UI 那一格优先显示用户自己的）；原图不自动删除
        （这一路只有读文件，没有任何 unlink/move/trash 的代码路径，回收站是工程记录）；
        近似分组与判定原因可见（`groups` 与每条 reason 的 method/value/threshold）。
        """
        unknown = set(p) - self.PICK_KEYS
        if unknown:
            emit({"event": "error", "error": f"pick 收到不认识的参数：{sorted(unknown)}"})
            return
        action = p.get("action", "state")
        if action not in self.PICK_ACTIONS:
            emit({"event": "error", "error": f"未知 pick action: {action}"
                  f"（可用：{'/'.join(self.PICK_ACTIONS)}，名单在 ready 的 pick_actions 里）"})
            return
        if action == "state":
            with self._doclock:
                rows = list(self._docs)
            have = [d for d in rows if d.get("pick")]
            emit({"event": "pick_state",
                  "rows": len(rows), "analyzed": len(have),
                  "failed": len([d for d in rows if d.get("pick_error")]),
                  "running": bool(self._picks is not None and self._picks.is_alive()),
                  "labels": sorted({lb for d in have for lb in (d["pick"].get("labels") or [])}),
                  "fingerprint": PK.fingerprint(), "algo": PK.ALGO_VERSION,
                  "thresholds": PK.thresholds_for_json(),
                  "sensitivities": {k: sorted(v) for k, v in self.PICK_SENS_TABLE.items()}})
            return
        if action == "stop":
            self._pick_stop.set()
            self.emit_session_state(pick_stopped=True)
            return
        sens = self._pick_sens(p)
        if sens is None:
            return
        try:
            edge = int(p.get("edge", self.PICK_EDGE))
            if not self.PICK_MIN_EDGE <= edge <= self.PICK_MAX_EDGE:
                raise ValueError(f"度量尺度 {edge} 越界（允许 {self.PICK_MIN_EDGE}"
                                 f"~{self.PICK_MAX_EDGE}，长边）")
        except (TypeError, ValueError) as e:
            emit({"event": "error", "error": f"pick 参数非法：{e}"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝挑图：两边都要解码与推理，"
                                            "同时跑的话跑靶读数就不再属于那一条通路（先 bench_stop）"})
            return
        if not self._docs:
            emit({"event": "error", "error": "底片条是空的：先 session scan/add"})
            return
        idxs = self._pick_targets(p)
        if idxs is None:
            return
        emit({"event": "pick_start", "targets": len(idxs), "edge": edge,
              "sensitivities": sens, "fingerprint": PK.fingerprint(), "algo": PK.ALGO_VERSION})
        self._start_picks(idxs, edge, p.get("model_dir"), sens)

    # ------------------------------------------------------------ 项目（LNX-P0-PROJECT / CORE-001、007、008）
    PROJECT_ACTIONS = ("create", "open", "save", "state", "tag", "trash")
    PROJECT_KEYS = {"cmd", "action", "name", "directory", "path", "doc", "index",
                    "tags", "label", "trashed", "force", "document_id"}

    def _project_state(self) -> dict:
        """项目段只有一个组装点：`session_state` 与四条 `project_*` 事件读到的必须同一份。

        写两处就会漂，而漂的表示是“刚刚存完但徽章还说未保存”——保存这件事的可信度
        全靠这个字段，它不能是一个估算值。

        字段名带 `_count` 不是凑字数：上一版这里叫 `dropped`，而 `project_saved` 里先写
        `"dropped": 清单`、后写 `**self._project_state()`（那份是个数），字典字面量
        后写的吃先写的——清单在事件里静默变成了一个整数。M2 审过的那一条同一形状。
        """
        p = self._project
        return {"open": p is not None, "path": self._project_path,
                "name": (p or {}).get("name"), "project_id": (p or {}).get("project_id"),
                "docs": len(self._docs) if p is not None else 0,
                "dirty": bool(self._project_dirty),
                "saved_ns": self._project_saved_ns,
                # 台账格数（不是“已写进文件的那一份”）：下一次 save 写的就是它，
                # 而 UI 的“N 个批次任务”必须与 task list 数出来的一致，不能两个答案
                "tasks": len(self._tasks),
                # 写手戳与“与当前环境是否一致”（P0-*-NEUTRAL 的“依赖版本一致”）：
                # 不一致时不拒开（旧工程必须能接着编辑），但必须把这件事说出口。
                "writer": (p or {}).get("writer"),
                "writer_match": ((p or {}).get("writer") == _current_writer())
                                 if p is not None else None,
                "dropped_count": len((p or {}).get("dropped") or []),
                "project_recovery": {"protocol":1,"runtime_verified":False,
                    "status":self._project_recovery_runtime.scheduler.status() if getattr(self,"_project_recovery_runtime",None) else {"phase":"idle"}},
                "managed_import": {"protocol":1,"runtime_verified":False,"modes":["reference","copy"],
                    "busy":bool(getattr(self,"_managed_import_controller",None) and self._managed_import_controller.active)},
                "source_relocation": {"protocol": 1, "exact_fingerprint": "sha256-full-file",
                    "runtime_verified": False,
                    "busy": bool(getattr(self, '_source_relocation_controller', None) and self._source_relocation_controller.active),
                    "requires_readback": bool(getattr(self, '_source_relocation_controller', None) and self._source_relocation_controller.uncertain)},
                **getattr(self, "_project_source_notice", {})}

    def _project_build(self, base: dict | None) -> tuple[dict, dict]:
        """把当前底片条编成一份待写的项目文档（不写盘），并报这一段的成本。

        资产表**每次重建**而不沿用上一份：沿用会让工程文件逐次保存单调变大（旧版本
        的资产没人引用也没人清），而这份文件是整份读进内存的。版本 id 用确定性的
        "live"，所以“当前配方”在文件里只有一格，而它的名字在多次保存之间稳定。

        全文件指纹在这里补算（只算缺的那些）并单独报耗时：把它藏在 load_image 的首帧
        里就会把“导一张图要多久”算成一个不存在的成本，而真机上一张 25 MB 的 DNG  hashing
        是几十毫秒量级。"""
        self._remember_current()
        t0 = monotonic_ns()
        hashed = 0
        prj = PJ.new_project((base or {}).get("name") or "未命名项目",
                             (base or {}).get("root") or os.path.expanduser("~"))
        if base:
            # 身份不随重存/改名变：工程列表靠它认“这是同一个项目”
            prj["project_id"] = base["project_id"]
            prj["created_ns"] = base.get("created_ns", prj["created_ns"])
            prj["source_assets"] = copy.deepcopy(base.get("source_assets",{}))
        dc = {"RepairOp": RepairOp, "LightOp": LightOp}
        for row in sorted(self._docs,key=lambda row:bool(row.get("copy_number",0))):
            if row.get("fingerprint") is None:
                try:
                    from .virtual_copy_source import fingerprint_for
                    row["fingerprint"] = fingerprint_for(row)[0]
                except OSError as e:
                    # 源文件没了：不把“我读不到”说成“它没变”，也不因此不存这一格
                    row["fingerprint"] = {"path": row["path"], "bytes": -1, "sha256": None,
                                          "head_sha256": None, "hash_level": "none",
                          "mtime_ns": 0, "readonly": True, "error": f"{type(e).__name__}: {e}"}
                else:
                    hashed += 1
            recipe = row["state"]
            if recipe.get("_precompute") is not None:
                # 关键点与面部掩膜**不随工程文件走**：它们不是用户画的，而是模型从这张图
                # 算出来的派生物——与本仓 RepairOp/LightOp “只存输入不存结果”同一条理由。
                # 不剔掉它的话代价是具体的：每个通道 (H,W) float32 在 207k 代理档上就是
                # ~830 KB，一百张图会把手上的工程文件顶到 `MAX_PROJECT_BYTES` 之外，
                # 而重开时本可以按 backend 重新推理（几百毫秒）拿回一模一样的东西。
                # 剔掉必须留话：否则“重开后面部微调按不动”会被读成引擎坏了。
                recipe = {**recipe, "_precompute": None}
                prj.setdefault("dropped", []).append(
                    {"path": row["path"], "at": "recipe._precompute",
                     "reason": "关键点/掩膜是模型产物（只存输入不存结果）："
                               "重开后按 precompute_backend 重新推理"})
            prow = PJ.add_doc(prj, row["path"], recipe, fp=row["fingerprint"],
                              tags=row.get("tags"), dc_types=dc,
                              budget=row.get("budget"), version_id=row.get("_project_version_id", row["recipe_version_id"]), trashed=bool(row.get("trashed")),
                              **{k:row[k] for k in ("document_id","source_asset_id","root_document_id","copy_number","recipe_version_id")})
            from .virtual_copy_project import save_row
            save_row(prj, row, prow, PJ)
            # 回收站与标签是**工程记录**：add_doc 新行时默认 False/None，这里把底片条
            # 那一格的实际值装回去（不装就是“存完重开，标都没了”）
            prow["trashed"] = bool(row.get("trashed"))
            prow["label"] = row.get("label")
        order = {row["document_id"]:i for i,row in enumerate(self._docs)}
        prj["docs"].sort(key=lambda row:order[row["document_id"]])
        # 任务台账跟着工程走（TASK-004/008）：persisted 那一份只存参数快照与结局，
        # 配方快照（带 numpy 图层）不存——所以重开后重试会被拒而不是偷换配方
        for t in self._tasks.values():
            t["persisted"] = True
        prj["tasks"] = [T.for_json(t) for t in self._tasks.values()]
        self._people_save(prj)
        from .virtual_copy_project import save_receipts
        save_receipts(self, prj)
        from .managed_import_project import save_receipts as save_import_receipts
        save_import_receipts(self, prj)
        prj["active_document_id"] = self._docs[self._doc_index]["document_id"] if 0 <= self._doc_index < len(self._docs) else None
        return prj, {"hash_ms": round((monotonic_ns() - t0) / 1e6, 2),
                     "fingerprinted": hashed}

    def _tasks_restore(self, prj: dict) -> list:
        """从工程文件读回任务台账（TASK-004/008）：一律 paused，不自动重跑。

        依赖变化在这一层就能判：那一批的输入路径不在新底片条里、或文件已不在
        磁盘上，就置 blocked_reason 并说清是哪几张。`tasks.from_json` 已经把
        “进程曾中断”那些“正在做”的说法一律回落到 paused，这里只补依赖那一句。"""
        self._tasks = {}
        paths = {d["path"] for d in self._docs}
        notes = []
        for obj in prj.get("tasks") or []:
            try:
                t = T.from_json(obj)
            except T.TaskError as e:
                notes.append({"reason": f"旧任务记录读不进来：{e}"})
                continue
            t["recipe_persisted"] = False
            gone = [p for p in t["inputs"].get("images") or [] if p not in paths
                    or not os.path.isfile(p)]
            if gone:
                t["blocked_reason"] = (f"依赖变了：{len(gone)} 个输入不在本工程或已不在磁盘上"
                                       f"（{gone[:3]}）——这一批不能重跑")
            else:
                t["blocked_reason"] = ("配方快照只活在本次会话：重开后请打开那张图再重新导出")
            self._tasks[t["task_id"]] = t
            notes.append({"task_id": t["task_id"], "state": t["state"],
                          "blocked": t["blocked_reason"]})
        return notes

    def _row_target(self, p: dict) -> dict | None:
        """按 index 或 path 找底片条那一格；找不到就 emit error 并递 None。"""
        if p.get("document_id") is not None:
            found = self._document_versions().find(self._docs, p["document_id"])
            if found is None: emit({"event":"error","error":"文档身份已变化，请刷新"}); return None
            return found[1]
        if p.get("index") is not None:
            try:
                idx = int(p["index"])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"project 的 index 不是整数：{p['index']!r}"})
                return None
            if not 0 <= idx < len(self._docs):
                emit({"event": "error", "error": f"index={idx} 不在底片条里（共 "
                       f"{len(self._docs)} 格）"})
                return None
            return self._docs[idx]
        if p.get("path"):
            try: index = self._index_of(p["path"])
            except ValueError as error:
                emit({"event":"error","error":str(error)}); return None
            row = self._docs[index] if index >= 0 else None
            if row is None:
                emit({"event": "error", "error": f"底片条里没有这一张：{p['path']}"})
            return row
        emit({"event": "error", "error": f"project {p.get('action')} 需要 index 或 path"
              "（它们是不同的东西：前者是底片条位置，后者是身份）"})
        return None

    def _recipe_needs_landmarks(self, st: dict) -> bool:
        """这一份配方要不要关键点（重开工程时用来定“要不要自动补一次分析”）。

        为什么只问这三件：关键点不随工程文件走（`_project_build` 剔的是派生物），而
        靠它们活着的只有形变层（含待重挂那一格）、多人图里“在改哪一张”的选型、以及
        掩膜通道/肤色作用域那两层。掩膜派生物可重算，但用户的通道/作用域选择必须恢复；
        不能以缺少派生物为由把用户选择清空——那就是 CORE-001“配方完整
        恢复”漏掉的那一层。这里多跑一次分析不贵（几百毫秒），少跑一次就是“重开少一半”。
        """
        if st.get("_grade_scope") == "objects" and LM.R.dependencies(LM.check(st.get("_local_masks"))["recipe"])[1]: return True
        if st.get("_channel") or st.get("_grade_scope") == "skin":
            return True
        if bool(st.get("_face_explicit")):
            return True
        # 人工账非空也要补这一次分析（PORTRAIT-006）：那几只关掉的、那几框补上的，都只有
        # 在名单重新算出来时才认得出对应的人。不补就是“重开工程后关掉的误检又回到名单里”
        _led = st.get("_face_manual") or {}
        if (_led.get("disabled") or _led.get("added")):
            return True
        if st.get("_deform_defer"):
            return True
        # 三层里任何一层有劲儿都要补这一次分析（判据与 `_deform_intent` 同一处）：
        # 只认 `_deform["amounts"]` 会漏掉“多人图重开后还没有脸盒，而默认/覆盖都在等”
        # 那一种——合成出来是零，而用户的活儿实实在在还在那两份里
        if LIPS.active(st.get("_lip_makeup")) or BROWS.active(st.get("_brow_shape")) or NOSES.active(st.get("_nose_shape")) or EYES.active(st.get("_eye_shape")) or MOUTHS.active(st.get("_mouth_shape")): return True
        if self._enhance_intent(st):
            # 眼牙那一层（PORTRAIT-009）与形变同一条：它的掩膜是从关键点重画的，
            # 没有关键点就没有这一层。少认这一格就是"重开工程后美白静消失"
            return True
        return self._deform_intent(st)

    def _source_fingerprint_drift(self, prj: dict) -> list:
        """P2-8：工程重开时逐张把源文件的现字节与当初存下的指纹对一遍，报"内容漂移"。

        过去这一步在 server 里从没被调用过（verify_fingerprint 只活在单测里），重开只查
        文件在不在（missing_sources）。于是"保存后原图被别的程序改了 / 被同步工具换了一版"
        这一整类漂移静默通过——用户拿旧几何的配方编辑一张已经不是当初那张的图，导出也不自知。

        判据取自存储时那一等（新版 project save 存的是 full）：文件在而 head/bytes/full
        任一对不上就是漂移。只 mtime 动（拷贝/同步工具改时间戳、字节没动）不算漂移——
        此时 head/bytes/full 全对得上，drifted 本身就是 False，不必再看 mtime_moved_only；
        缺文件不在此计（已由 missing 报）。
        """
        changed: list = []
        for prow in prj["docs"]:
            fp = (prj.get("source_assets",{}).get(prow.get("source_asset_id"),{}).get("fingerprint") or prow.get("fingerprint"))
            if not isinstance(fp, dict) or fp.get("hash_level") in (None, "none"):
                continue                      # 这一格没指纹可核（旧版从没算过的降级行）
            v = PJ.verify_fingerprint(prow["path"], fp)
            if not v["exists"]:
                continue                      # 缺文件已由 missing 报，不重复计
            drifted = (not v["head_match"]) or (not v["bytes_match"]) \
                or (v.get("full_match") is False)
            if drifted:
                changed.append({"path": prow["path"], "level": v["level"],
                                "head_match": bool(v["head_match"]),
                                "bytes_match": bool(v["bytes_match"]),
                                "full_match": v["full_match"]})
        return changed

    def cmd_project(self, p: dict):
        from .project_package_project_commands import handle
        return handle(self, p, emit, _current_writer)


    # ------------------------------------------------------------ 导入期预计算
    def _precompute_ready_event(self, pc, info, *, build_ms: float, infer_ms: float,
                                attach_ms: float, total_ms: float, replayed_for: str | None = None):
        """precompute_ready 只在这里组装一次。

        两处各写一份的必然结果是漂移，而且漂的方向永远是“设备切换那条臂少一个字段”：
        重挂那条路径先前就没有 build_ms/infer_ms/total_ms，UI 把它们声明为必存字段
        就会读到 undefined。现在两条臂的事件形状相同，差别只写在 replayed_for 里。
        """
        ev = {"event": "precompute_ready", **pc.meta(self._vram.h, self._vram.w),
              "resident_device": info["resident_device"],
              "mask_bytes": info["mask_bytes"], "landmark_bytes": info["landmark_bytes"],
              "active_channel": self._channel,
              "build_ms": build_ms, "infer_ms": infer_ms,
              "attach_ms": attach_ms, "total_ms": total_ms,
              # 多人图那一格（PORTRAIT-003）：分析完才知道有几张脸、这次挂上的是哪一张。
              # 宿主的面板要在这里就把“能选几个人”画出来，而不是等一次 face list——
              # 重开工程那条路就是靠这条事件把选型认回来的（doc_state 发在分析之前）。
              "face": self._face_state()}
        if replayed_for:
            ev["replayed_for"] = replayed_for
        return ev

    def _drop_grade_scope(self, from_scope: str, why: str) -> None:
        """Retain local intent when derived masks are unavailable; never broaden."""
        emit({"event": "engine_warn", "warn": f"局部调色 {from_scope!r} 暂停，未扩大到全图（{why}）"})
        self._grade_scope = from_scope
        if self._vram is not None:
            self._vram.grade_scope = from_scope
            if from_scope == "brush": self._vram._grade_mask_gpu = None

    def _rehang_grade_scope(self, *, replayed_for: str) -> None:
        """把存下的调色作用域/区域重挂到**当前会话**（换设备、切文档、撤销重做都走这里）。

        三条臂各有归属：all 什么都不做；brush 靠存下的区域（尺寸对不上就整条放下）；
        skin 靠掩膜，而掩膜要等 `_rehang_precompute` 挂上才存在 —— 所以它在这里可能被
        **推迟**而不是判失败（掩膜挂上后还会再调一次）。推迟不等于说谎：等不到掩膜的
        那种局面（本档就没有预计算产物）当场退回全图。

        不写两份的原因与 `_rehang_precompute` 一样：会话新建了而作用域没重挂，新会话
        里这一层是全图，屏幕会把局部调色算成全局调色，而 grade_done 里报的还是 brush。
        """
        pipe = self._vram
        scope = str(self._grade_scope or "all")
        if pipe is None or scope == "all":
            return
        if scope not in GRADE_SCOPES:
            self._drop_grade_scope(scope, f"{replayed_for}：未知作用域")
            return
        if scope == "objects":
            LM.sync(self); return
        if scope == "skin":
            if self._precompute is None:
                self._drop_grade_scope(scope, f"{replayed_for}：本档没有人脸掩膜可用")
                return
            if pipe.masks_gpu is None:
                return          # 等 _rehang_precompute 挂上掩膜后再试一次
            try:
                pipe.set_grade_scope("skin")
            except (ValueError, RuntimeError) as e:
                self._drop_grade_scope(scope, f"{replayed_for}：{e}")
            return
        # brush：区域是代理帧坐标的 uint8，换会话必须重新上一次显存
        if self._grade_mask is None:
            self._drop_grade_scope(scope, f"{replayed_for}：画笔区域不在了")
            return
        try:
            pipe.set_grade_mask(self._grade_mask, mode="replace")
            pipe.set_grade_scope("brush")
        except (ValueError, RuntimeError) as e:
            # 尺寸对不上（工程档存的是另一档代理尺寸）也走这里：那份区域对本会话没有
            # 任何意义，留着它只会让下一次重挂再撞一遍
            self._drop_grade_scope(scope, f"{replayed_for}：{e}")


    # ---- PORTRAIT-009：眼牙局部增强 -----------------------------------------
    ENHANCE_KEYS = {"cmd", "action", *ENH.AMOUNT_KEYS}
    ENHANCE_ACTIONS = ("set", "clear")

    def _enhance_intent(self, st: dict | None = None) -> bool:
        """这一份状态里有没有"用户要一层眼牙增强"的意图（有非零的子功能值）。

        与 `_deform_intent` 同一类判据，独立写一份而不是复用：形变看的是三种 kind 的
        合成值（默认 + 逐张覆盖），而这一层看的是三个子功能的独立值，两者字段结构不同，
        硬套会造出"一个函数两种语义"的那种可读性债务。
        """
        en = (st if st is not None else self._capture_state())["_enhance"]
        return WSTATE.active_enhance(en.get("amounts") or {})

    def _drop_enhance(self, why: str) -> None:
        """放下会话里那一场（参数与脸盒留在文档状态里）。"""
        if self._vram is not None:
            self._vram.clear_enhance_field()
        self._enhance = dict(amounts=dict(self._enhance["amounts"]), built=False, box=self._enhance.get("box"))

    def _restore_enhance(self, prev: dict) -> None:
        """被拒/回滚时把文档状态与会话那一场一起退回上一版（不留半截）。"""
        self._enhance = {"amounts": dict(prev.get("amounts") or {}),
                         "built": bool(prev.get("built")), "box": prev.get("box")}
        self._enhance_defer = bool(prev.get("_defer"))
        if self._vram is None:
            return
        if not WSTATE.active_enhance(self._enhance["amounts"]):
            self._vram.clear_enhance()
            self._vram.set_enhance(self._enhance["amounts"])
        elif prev.get("built") and self._precompute is not None:
            try:
                self._vram.build_enhance(self._precompute.landmarks, amounts=self._enhance["amounts"])
                self._vram.set_enhance(self._enhance["amounts"])
            except Exception:                            # noqa: BLE001
                self._vram.clear_enhance_field()
        else:
            self._vram.clear_enhance_field()

    def _rehang_enhance(self, pc=None, *, replayed_for: str, write_frame: bool = True) -> None:
        """关键点回来后把这一层接回去（重开工程 / 迁会话 / 换后端 / 换人选都走这里）。

        认的是**脸盒**而不是序号：这一层的掩膜是从那一张脸的 478 点画出来的，换人时若
        不认脸盒就会把 A 的美白静默涂到 B 身上（SCOPE-001 拦的同一件事）。认不回那一张
        就整场放下并说清原因——参数留着，因为"用户改过什么"与"引擎现在认不认得人"
        是两件事（PORTRAIT-004 定下的分层）。
        """
        lit_before = bool(self._vram is not None and self._vram.has_enhance())
        if self._people_managed():return
        if not self._enhance_intent():
            if self._enhance["built"]:
                self._drop_enhance(f"{replayed_for}：参数已经全是 0，这一层没有活")
                if lit_before and write_frame:
                    self._refresh_frame_after_drop("enhance")
            self._enhance_defer = False
            return
        if self._vram is None or not self._image_loaded:
            return
        pc = pc if pc is not None else self._precompute
        want_box = self._enhance.get("box")
        if pc is None:
            # 没关键点：存住等下一次分析（不归零——那是 CORE-001 已经付过学费的那一格）
            self._drop_enhance(f"{replayed_for}：没有关键点可重画掩膜")
            self._enhance_defer = True
            self._emit_enhance_state("defer",
                                     reason="这一层的掩膜要从 478 点重画，而本会话还没有关键点："
                                          "参数已存住，跑一次 precompute 就接回来")
            return
        if getattr(pc, "backend", None) == "synthetic":
            self._drop_enhance(f"{replayed_for}：synthetic 模板几何")
            self._emit_enhance_state("invalidate",
                                     reason="关键点来自 synthetic 模板几何（网格占位，不是脸形）："
                                          "掩膜画不出可信的眼/牙位置，这一层整层放下",
                                     dropped_amounts=self._enhance["amounts"])
            if lit_before and write_frame:
                # 与形变那两条臂同一条理由：层放下了而帧没重画，屏幕上还挂着刚才的美白
                self._refresh_frame_after_drop("enhance")
            return
        if want_box is not None and self._person_key(self._face_box) != tuple(
                float(v) for v in want_box):
            # 换人了：这一层不属于现在选定的那一张
            self._drop_enhance(f"{replayed_for}：这一层挂在另一张脸上")
            self._emit_enhance_state("invalidate",
                                     reason="这一层挂在另一张脸上（按脸盒认的）：不拿 A 的参数"
                                          "静默服务 B。选回那一张就自动接回来；要改这一张请重新设值",
                                     dropped_amounts=self._enhance["amounts"])
            if lit_before and write_frame:
                self._refresh_frame_after_drop("enhance")
            return
        try:
            info = self._vram.build_enhance(pc.landmarks, amounts=self._enhance["amounts"])
            self._vram.set_enhance(self._enhance["amounts"])
            info = self._vram._enhance_payload(layer_recomputed=True)
        except (ENH.EnhanceError, ValueError, RuntimeError) as e:
            self._drop_enhance(f"{replayed_for}：重画失败")
            self._emit_enhance_state("invalidate",
                                     reason=f"用这批关键点重画掩膜失败，已整层放下："
                                            f"{type(e).__name__}: {e}",
                                     dropped_amounts=self._enhance["amounts"])
            return
        self._enhance = dict(amounts=dict(self._enhance["amounts"]), built=True,
                             box=self._person_key(self._face_box))
        self._enhance_defer = False
        fr = None
        render_ms = 0.0
        if write_frame and bool(info.get("enhance_lit")) and self.shm is not None \
                and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
            try:
                fr = self._write_current_frame("enhance")
                render_ms = fr.pop("render_ms", 0.0)
            except Exception as e:                        # noqa: BLE001
                emit({"event": "engine_warn", "warn": f"眼牙层重挂后补帧失败：{e}"})
        self._emit_enhance_state("rebuild", info=info, render_ms=render_ms)
        if fr is not None:
            emit(fr)

    def _emit_enhance_state(self, action: str, *, info: dict | None = None,
                            render_ms: float = 0.0, total_ms: float = 0.0,
                            reason: str | None = None, dropped_amounts: dict | None = None,
                            note: str | None = None) -> None:
        """enhance_done 只在这里组装一次（命令、重挂、放下三条臂共用一份形状）。

        与 `_emit_deform_state` 同一条理由：两处各写一份，漂的方向永远是"后接的那条臂
        少一个字段"，而 TS 把字段声明成必存——谎报发生在 JSON 边界上，编译期抓不到。
        """
        payload = dict(info or (self._vram._enhance_payload(layer_recomputed=False)
                                if self._vram is not None else {}))
        payload.update({
            "event": "enhance_done",
            "action": action,
            "amounts": {k: float(v) for k, v in self._enhance["amounts"].items()},
            "built": bool(self._enhance["built"]),
            "defer": bool(self._enhance_defer),
            # 平铺的 lit 与 deform_done 同形：它问的是"屏幕上这一层现在真的有力吗"，
            # 而 `built` 只说"场挂上了"。闭嘴样本的牙齿那一格就是 built 而 lit 的另一半
            # （场里没额度）。宿主读嵌套那一份（enhance_*），面板与测试读平铺。
            "lit": bool(payload.get("enhance_lit")),
            "gated_px": {k: int(v) for k, v in (payload.get("enhance_gated_px") or {}).items()},
            "person_box": (list(self._enhance["box"]) if self._enhance.get("box") else None),
            "render_ms": round(render_ms, 2),
            "total_ms": round(total_ms, 2),
        })
        if reason is not None:
            payload["reason"] = reason
        if dropped_amounts is not None:
            payload["dropped_amounts"] = {k: float(v) for k, v in dropped_amounts.items()}
        if note is not None:
            payload["note"] = note
        emit(payload)

    def cmd_fabric(self, p: dict): return FABRIC.handle(self, p, emit)

    def cmd_enhance(self, p: dict):
        """眼牙局部增强（LNX-PORTRAIT-009）：眼白提亮 / 虹膜增强 / 牙齿美白，各自独立启停。

        铁律逐条沿用 cmd_grade/cmd_deform：参数先全量校验、跑靶互斥、被拒整条不生效、
        渲染抛错就成对回滚、事件只有一个组装点。这一层独有的两条：

        1. **必须有真关键点**（synthetic 模板几何按拒绝处理）：这一层的掩膜画在虹膜圆盘
           与唇齿多边形上，占位几何画不出可信位置——宁可拒，也不画一张"看上去像眼睛"的
           椭圆（那就是 DoD 严禁的那种假效果）。
        2. **点火了而一个像素也没盖到不是错误**：闭嘴样本的牙齿那一格、两只眼都被几何
           校验拒掉的极端侧脸，命令成功返回、`lit=false`、逐子功能写明原因。把这做成
           报错会让 UI 只能弹一个"失败"，而用户想知道的恰恰是"为什么牙那格没动"。
        """
        if self._people_managed():return self._people_legacy("lnx.enhance.v1",p,emit)
        unknown = sorted(set(p) - self.ENHANCE_KEYS)
        if unknown:
            emit({"event": "error", "error": f"enhance 收到不认识的参数：{', '.join(unknown)}"
                  "（可用参数名单见 ready 的 enhance_subs，已有高光支持 catchlight_left / catchlight_right）"})
            return
        action = p.get("action", "set")
        if action not in self.ENHANCE_ACTIONS:
            emit({"event": "error", "error": f"未知 enhance action: {action}"
                  f"（可用：{'/'.join(self.ENHANCE_ACTIONS)}）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 enhance：先 bench_stop"})
            return
        given = {k: p[k] for k in ENH.AMOUNT_KEYS if p.get(k) is not None}
        if action == "set" and not given:
            emit({"event": "error", "error": "enhance set 什么也没给：子功能里至少给一个，"
                  "或者走 clear 把整层关掉"})
            return
        merged = dict(self._enhance["amounts"])
        if action == "clear":
            merged = {k: 0.0 for k in ENH.AMOUNT_KEYS}
        else:
            merged.update(given)
        try:
            amounts = ENH.check_amounts(merged)
        except ENH.EnhanceError as e:
            emit({"event": "error", "error": f"enhance 被拒，整条不生效：{e}"})
            return
        t_start = monotonic_ns()
        prev = {"amounts": dict(self._enhance["amounts"]), "built": bool(self._enhance["built"]),
                "box": self._enhance.get("box"), "_defer": bool(self._enhance_defer)}
        pc = self._precompute
        if WSTATE.active_enhance(amounts):
            # SCOPE-001：这一层的作用面是"某一个人"。多人图里没显式选定就不许替用户选
            blocked, why = self._face_guard()
            if blocked:
                # 这一层的作用面也是“某一个人”，所以放行判据与 deform 同一个出处：
                # 两边各自拼一遍就会在“人工关掉一只误检”之后分了家（PORTRAIT-006）
                emit({"event": "error", "error": why})
                return
            if pc is None:
                self._enhance = dict(amounts=amounts, built=False, box=None)
                self._enhance_defer = True
                self._vram.clear_enhance_field()
                self._emit_enhance_state("defer",
                                         reason="本会话还没有关键点：参数已存住（不进画面、不静默丢弃），"
                                                "跑一次 precompute 会自动接回这一层",
                                         total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
                return
            if getattr(pc, "backend", None) == "synthetic":
                emit({"event": "error", "error":
                      "enhance 拒绝 synthetic 后端的关键点：那是网格占位几何、不是脸形，"
                      "画不出可信的虹膜圆盘与唇齿多边形。要这一层请用 mediapipe 后端"
                      "（template/synthetic 只服务通路回归）"})
                return
        try:
            if WSTATE.active_enhance(amounts):
                # build_enhance 的返回值不直接用：set_enhance 之后那份才是最终状态，
                # 而两处都从同一个 `_enhance_payload` 组装（事件只有一个形状来源）。
                # 场只在几何变了的时候重画（关键点没变而滑块动了 = 只改系数）。
                # 这条复用判据不是性能偏好：它是"拖滑块时到底有没有重算掩膜"那一句
                # 产品主张的实现，而性能那一臂把它当回归判据（拖动期间 layer_recomputed
                # 必须一路 False）。
                rebuilt = self._vram.enhance_needs_rebuild(pc.landmarks, amounts=amounts)
                if rebuilt:
                    self._vram.build_enhance(pc.landmarks, amounts=amounts)
                self._vram.set_enhance(amounts)
                info = self._vram._enhance_payload(layer_recomputed=rebuilt)
                self._enhance = dict(amounts=dict(amounts), built=True,
                                     box=self._person_key(self._face_box))
                self._enhance_defer = False
            else:
                self._vram.clear_enhance()
                info = self._vram.set_enhance(amounts)
                self._enhance = dict(amounts=amounts, built=False, box=None)
                self._enhance_defer = False
        except (ENH.EnhanceError, ValueError, RuntimeError, MemoryError, OSError) as e:
            self._restore_enhance(prev)
            emit({"event": "error", "error": f"人物增强未提交，已保留上一配方：{type(e).__name__}: {e}"})
            return
        try:
            fr = self._write_current_frame("enhance")
        except Exception as e:
            self._restore_enhance(prev)
            try:
                back = self._write_current_frame("enhance")
                back.pop("render_ms", None)
                emit(back)
            except Exception:                            # noqa: BLE001
                emit({"event": "engine_warn", "warn": "眼牙增强回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"眼牙增强渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms", 0.0)
        # 账要取**渲染之后**那一份：`enhance_ms` 说的是"最近一帧里这一层花了多少"，
        # 而那一次渲染就是 `_write_current_frame`。取在渲染前，第一条命令必然报出一个
        # 恒 0 的计时（那一刻这一层还没进过帧通路），于是"这一层是毫秒级局部重放"这句
        # 承诺一份证据都没有——m5 第 8 臂的 `0 < enhance_ms` 判据就是这样变成假红的
        # （真机实测：代理档稳态 1.06 ms/帧，首次 250 ms 是 CUDA 惰性建核）。
        # 与 cmd_deform 同一条次序：先出帧，后组装那一帧的账。
        if info is not None and self._vram is not None:
            info = self._vram._enhance_payload(
                layer_recomputed=bool(info.get("layer_recomputed")),
                build_ms=float(info.get("enhance_build_ms", 0.0)) or None)
        # info 必须**按关键字**传：_emit_enhance_state 的签名是 (action, *, info, …)，
        # 位置传法在 import 时不报错、第一条命令才炸 TypeError——这就是端到端臂存在的理由
        # （库层 41 条全绿也没碰到它，因为它在 server 的调用点上）。
        self._emit_enhance_state(action, info=info, render_ms=render_ms,
                                 total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
        emit(fr)



    def _rehang_precompute(self, *, replayed_for: str) -> bool:
        """把 CPU 原件形态的预计算产物挂到**当前会话**上。

        换设备与切文档走同一段，不写两份：会话是新张量而掩膜没重挂时，下一条带
        channel 的 set_strength 会被 mask_names 拒掉，而报表仍写着“有 skin 通道”——
        UI 说“没掩膜”的同时引擎里那张掩膜并不存在，两边各自自洽。失败后清除派生掩膜与单位场，
        但保留用户请求的作用域；渲染时暂停缺少掩膜的效果，不扩大到全图。
        """
        if self._precompute is None or self._vram is None:
            return False
        t_p = monotonic_ns()
        try:
            info = self._vram.load_face(self._precompute)
        except Exception as e:
            self._fence_current_document()
            emit({"event": "error",
                  "error": f"会话重挂预计算产物失败，相关效果暂不生效，编辑参数已保留（"
                           f"{type(e).__name__}）：{e}"})
            self._vram.clear_face()
            self._precompute = None
            self._precompute_backend = None
            # Keep the user's requested scope. Rendering suspends the masked effect
            # until its mask is restored; None would silently turn it into a global edit.
            # 会话里的生效值与单位场一起放下（这一张现在确实没劲儿），而用户的两份层级
            # （PORTRAIT-004）不是模型派生物，不在“一并清除”的范围里：留着，下一次成功的
            # precompute 会按脸盒接回来。defer 只在合成结果非零时留真（全零留真是说谎）
            self._deform = dict(amounts=self._effective_deform_amounts(), built=False)
            self._deform_defer = any(abs(float(v)) > 0.0
                                     for v in self._deform["amounts"].values())
            # 掩膜没了，靠它活着的那个调色作用域也必须一起放下（库层 clear_face 已经把
            # vram 那一侧退回 all，这里不放宿主字段就会继续报“只调皮肤”）
            if str(self._grade_scope) == "skin":
                self._drop_grade_scope("skin", f"{replayed_for}：掩膜重挂失败")
            return False
        emit(self._precompute_ready_event(
            self._precompute, info,
            # 重挂没重新算：建图与推理都是 0，不是“没测到”。这里给 0.0 而不是
            # 缺字段，是为了让两条臂的事件形状完全一致——UI 那边一旦按必存字段
            # 读，少一个键就会在报表上变成 undefined 而无人报错
            build_ms=0.0, infer_ms=0.0,
            attach_ms=round((monotonic_ns() - t_p) / 1e6, 2),
            total_ms=round((monotonic_ns() - t_p) / 1e6, 2),
            replayed_for=replayed_for))
        # 掩膜刚挂上，这里才是 skin 作用域能落地的时刻（_attach_pipeline 里那次可能被推迟）。
        # 放在 ready 事件之后：事件序列先说“掩膜有了”，再说“调色只吃那一片”。
        self._rehang_grade_scope(replayed_for=replayed_for)
        # 眼牙层（PORTRAIT-009）：掩膜从这批关键点重画。放在 ready 事件之后，与上面
        # scope 那条同一次序约定（事件先说"关键点有了"，再说"那一层接回来了"）
        self._rehang_enhance(self._precompute, replayed_for=replayed_for)
        return True

    def cmd_precompute(self, p: dict):
        """导入期一次性预计算：478 点关键点 + 语义掩膜，算完直接常驻显存。

        三个耗时分开报，因为它们是三种成本：后端建图/首次推理是每进程一笔，
        逐图推理是每张图一笔，H2D 挂载是代理帧字节数的一笔。混成一个总数就分不出
        下一步该优化谁。

        不许静默降级：点名要 mediapipe 而后端/模型不在，直接报错；只有 `auto` 允许回落，
        且回落必须发 engine_warn —— 上轮「CPU 会话标 cuda」就是少了这一层。
        """
        from . import face as face_mod

        if not self._image_loaded or self._vram is None or self._src_rgb is None:
            emit({"event": "error", "error": "precompute 需要先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝预计算：先 bench_stop"})
            return
        self._fence_current_document()
        backend = p.get("backend", "auto")
        t0 = monotonic_ns()
        try:
            fn = face_mod.build(backend, p.get("model_dir"))
            if self._creative_base is not None and fn.name != "mediapipe":
                raise ValueError("创意回流重新分析需要真实 MediaPipe 后端，不接受模板替代")
        except face_mod.MissingBackend as e:
            emit({"event": "error", "error": f"预计算后端不可用({backend}): {e}"})
            return
        except ValueError as e:
            emit({"event": "error", "error": f"预计算参数非法: {e}"})
            return
        t1 = monotonic_ns()
        if backend == "auto" and fn.name != backend and getattr(fn, "notes", None):
            emit({"event": "engine_warn", "warn": f"auto 回落 {fn.name}: {fn.notes[-1]}"})
        try:
            from .creative_derived_source import analysis_rgb, stamp_precompute
            analysis_input = analysis_rgb(self)
            pc = stamp_precompute(self, fn(analysis_input), analysis_input)
        except Exception as e:
            emit({"event": "error", "error": f"预计算失败({type(e).__name__}): {e}"})
            return
        t2 = monotonic_ns()
        # 通道校验必须上移到“上显存”之前。放在 load_face 之后报错会留下半截状态：
        # 掩膜已常驻、_precompute 已赋值、但 precompute_ready 从没发过——宿主只收到一个 error，
        # 下次换设备却突然收到一个它从未见过初始值的 replayed_for；而 UI 报“没掩膜”的同一
        # 时刻，引擎里那张掩膜是可用且真的在参与渲染的。
        channel = p.get("channel")
        available = sorted(pc.masks)
        if channel and channel not in available:
            emit({"event": "error", "error": f"没有掩膜通道 {channel}"
                  f"（可用：{', '.join(available) or '无'}）"})
            return
        # 人工账先重贴（PORTRAIT-006）：它必须排在 `_preserve_face_choice` 之前，因为
        # “还剩几个可编辑的人”要先算对，选型与放行判据才是在同一份名单上做的
        pc, _manual_ledger = self._reapply_face_manual(pc, backend=fn)
        try:
            # 多人图里“上次显式选了哪一张”要跟着这次分析走（PORTRAIT-003）。放在上显存
            # 之前：上传的关键点与后面报出去的 face_index 得是同一张脸。
            pc = self._preserve_face_choice(pc)
            info = self._vram.load_face(pc)
        except Exception as e:
            emit({"event": "error", "error": f"掩膜上显存失败({type(e).__name__}): {e}"})
            return
        t3 = monotonic_ns()
        self._precompute = pc
        self._precompute_backend = pc.backend
        if self._creative_base is not None: self._people_sync(strict=True)
        if channel:
            self._channel = channel
        emit(self._precompute_ready_event(pc, info,
              build_ms=round((t1 - t0) / 1e6, 2),
              infer_ms=round((t2 - t1) / 1e6, 2),
              attach_ms=round((t3 - t2) / 1e6, 2),
              total_ms=round((t3 - t0) / 1e6, 2)))
        # 预计算完不重发帧：默认渲染路径不看掩膜，重发只能多一个变量进测量。
        # 要看掩膜作不作数，用 set_strength + channel。
        # 形变层是例外：它的单位场就是从这批关键点解出来的，关键点一走它就是
        # 无源之水（M2-b 审查项 2，口径见 _rebuild_deform_for_landmarks）。
        self._rebuild_deform_for_landmarks(pc)
        # 眼牙层同理是"关键点是它的唯一来源"的那一层（PORTRAIT-009）：换后端重算后
        # 不重画掩膜，就是"上报说 mediapipe、屏幕上还在按模板几何美白"
        self._rehang_enhance(pc, replayed_for="precompute")
        if self._fabric_amount: emit(self._write_current_frame("fabric_rebuild"))
        self.emit_session_state()

    def _rebuild_deform_for_landmarks(self, pc, *, write_frame: bool = True) -> None:
        """关键点更新后重建已常驻的形变层：滑块值保留，单位场跟着新几何走。

        上一版这里什么都不做，于是“precompute(template) → deform set slim=0.9 →
        装上 mediapipe 再 precompute(mediapipe)”之后 cmd_deform 看见 built=True 就
        不再重解：形变还在用肤色盒模板的几何瘦这一张脸，而 deform_done 把
        landmark_backend 报成 mediapipe——上报与画面双向错配，而且是“看不出错”那一类。
        库层 vram.clear_face 的注释早就写明“关键点一走单位场就是无源之水”，但命令层
        没接线，所以它一直是没人走的死代码。

        先清再建：新后端解不出层时，旧几何绝不能继续服务。滑块值不重置：换后端是
        “同一张脸量得更准”，不是“用户改了主意”，把用户的作品按引擎内部事件归零是
        另一种静默降级。解不出时发 action=invalidate，UI 那条必须把滑块跟着归零。

        `built=False` 而 `_deform_defer=True` 也算“有层”：那是重开工程/迁会话存住的那一份
        用户意图（CORE-001），关键点一回来就该补上。不认这一格就是“重开后面部微调静消失”。
        """
        if self._people_managed():return
        if not self._deform_intent():
            # 三层（生效值 / 全人物默认 / 逐张覆盖）都没劲儿就是真没这一层：不建、不报
            return
        if self._person_key(self._face_box) is None:
            # 没有“那一张”（多人图还没选定，或这一轮没探出脸盒）：两份层级原样留着当用户
            # 意图，而会话里那一层必须放下——拿“全人物默认”去服务一张说不出是谁的脸，正是
            # SCOPE-001 拦的那件事（上一版这里会照旧建层，等于把默认盖到名单里第 0 张脸上）
            if self._deform["built"]:
                self._vram.clear_deform()
            was_lit = bool(self._vram.has_deform())
            self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
            self._deform_defer = False
            self._emit_deform_state("invalidate",
                                    reason="这一轮没有可服务的那一张（多人图还没 `face select` "
                                           "选定，或没探出脸盒）：全人物默认与逐张覆盖都留着，"
                                           "选定那一张后自动接上")
            if was_lit and write_frame:
                self._refresh_frame_after_drop("deform")
            return
        amounts = dict(self._effective_deform_amounts())
        was_lit = bool(self._vram.has_deform())
        self._vram.clear_deform()
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        self._deform_defer = False
        if pc.backend == "synthetic":
            emit({"event": "engine_warn",
                  "warn": "关键点后端换成 synthetic（网格占位几何），会话里的形变层已放下；"
                          "全人物默认与逐张覆盖按脸盒留着，换成真后端再分析一次就接回来"})
            self._emit_deform_state("invalidate", reason="synthetic 占位几何不能按脸形语义取点",
                                    dropped_amounts=amounts)
            if was_lit and write_frame:
                self._refresh_frame_after_drop("deform")
            return
        try:
            built = self._vram.build_deform(pc.landmarks)
            state = self._vram.set_deform_amounts(amounts)
        except (DeformGeometryError, ValueError, RuntimeError) as e:
            self._vram.clear_deform()
            emit({"event": "engine_warn",
                  "warn": f"用新关键点重建形变层失败，已整层清除：{type(e).__name__}: {e}"})
            self._emit_deform_state("invalidate", reason=f"重建失败：{e}",
                                    dropped_amounts=amounts)
            if was_lit and write_frame:
                self._refresh_frame_after_drop("deform")
            return
        self._deform = dict(amounts=dict(state["amounts"]), built=True)
        # 层真的变了（有非零滑块）就必须补一帧：不补就是“引擎已按新几何形变，
        # 屏幕还是旧像素”，而 precompute_ready 里看不出画面错开
        render_ms = 0.0
        fr = None
        if write_frame and bool(state["lit"]) and self.shm is not None \
                and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
            try:
                fr = self._write_current_frame("deform")
                render_ms = fr.pop("render_ms")
            except Exception as e:
                # 补帧失败不能把整条 precompute 拖死（预计算本身已成立），但必须说清
                # “引擎已按新几何重建形变层、屏幕还是旧帧”这件事
                emit({"event": "engine_warn", "warn": f"形变层重建后补帧失败：{e}"})
        # 事件次序与 cmd_deform 一致：先报状态、后报帧。反过来会让“等 deform_done”的
        # 调用方把中间那条 frame 事件吞掉，下一帧就再也等不到（本轮真踩过）
        self._emit_deform_state("rebuild", build=built, render_ms=render_ms)
        if fr is not None:
            emit(fr)

    def _emit_deform_state(self, action: str, *, build: dict | None = None,
                           render_ms: float = 0.0, total_ms: float = 0.0,
                           reason: str | None = None,
                           dropped_amounts: dict | None = None,
                           scope: str = "all") -> None:
        """deform_done 只在这里组装一次（cmd_deform 与关键点重建/清除三条臂共用）。

        与 _precompute_ready_event 同一条理由：两处各写一份，漂的方向永远是“后接的那
        条臂少一个字段”，而 TS 把字段声明成必存——谎报发生在 JSON 边界上，编译期抓不到。
        """
        pipe = self._vram
        from . import face as face_mod       # 判据只写在 face.geometry_warning 里
        ev = {"event": "deform_done", "action": action,
              "amounts": dict(pipe.deform_amounts),
              # 作用层与层级那一份账（PORTRAIT-004）：`amounts` 说的是“会话现在在渲染
              # 什么”，而“默认是多少、这一张被单独改了几格”只有这里说得出——两条臂
              # （cmd_deform / 关键点重建）共用这一个组装点，写两处必然漂
              "scope": scope,
              **self._layered_deform_state(),
              "built": bool(pipe.deform_units),
              "lit": bool(pipe.has_deform()),
              "deform_builds": int(pipe.deform_builds),
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "bytes_deform": int(pipe.deform_resident_bytes()),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              # 关键点出自哪个后端必须原样上报：template 是“按肤色盒摆的模板”，
              # 贴合度不验收。UI 拿不到这个数就会把模板拟合当成真检测给用户看。
              "landmark_backend": (self._precompute.backend if self._precompute else None),
              # 作用面：各形变里最宽的那一种会动到画幅的多少。它是“瘦脸不许
              # 拖走背景”这句话在**当前这张图**上的直接读数：窗口参数只能说明圆心
              # 与半径，几何落错了地方时同一个公式会盖住整幅（真人照片上量到 98.6%）。
              # 没建层时给 0.0 而不是缺键：UI 把这两个字段当必存，缺键就是 undefined。
              "support_share": round(max([float((pipe.deform_meta.get(k) or {})
                                                .get("support_share", 0.0))
                                          for k in KINDS] or [0.0]), 4),
              # 几何看上去像不像一张脸（与 precompute_ready 同一个判据、同一个出处）
              "geometry_warning": bool(face_mod.geometry_warning(
                  self._precompute.face_box) if self._precompute else False),
              # 后端自己对几何可信度的意见（模板拟合贴到整幅边界时不为空）。
              # 它必须随事件走：同一套代码在合成靶上不说、在真人照片上也不说，
              # 就正是本仓反复防止的“看不出错”那一类。
              "landmark_notes": list(self._precompute.notes) if self._precompute else [],
              "device": str(pipe.device), "strength": self._strength}
        if build is not None:
            ev["build"] = build
        # 待重挂那一格也得随事件走（CORE-001）：`amounts` 说的是“会话现在真的在渲染什么”，
        # 而用户那一层的值在 `deferred_amounts` 里。合成一个字段就会说谎：要么把“没在
        # 渲染”说成“没这一层”，要么把“已存住”说成“已生效”。
        ev["defer"] = bool(self._deform_defer)
        ev["deferred_amounts"] = (dict(self._deform["amounts"]) if self._deform_defer else None)
        if reason:
            ev["reason"] = reason
        if dropped_amounts:
            # 失效那一条要让用户看到“刚才拖的是多少”：只报 lit=false 的话，滑块弹回
            # 零像出了 bug，而实际是后端换了
            ev["dropped_amounts"] = dict(dropped_amounts)
        emit(ev)

    def cmd_set_strength(self, p: dict):
        """滑块动一下：只重算系数，不重解码也不重上传。返回一帧。

        channel 可以指到某个常驻掩膜通道（只换张量引用，不重传任何东西），这就是
        M1-3c「拖滑块零推理」的入口。
        """
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            # 会话与缓冲不同尺寸时 write_frame 只会报“字节数不对”，看不出是换档没走完
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        # 跑靶互斥：_wlock 只护“写 shm”那一步，护不到 frame_gpu。跑靶线程是
        # pack(frame_gpu) → read_back() → 锁内写 shm，这里的 render 也写同一个 frame_gpu；
        # 插在中间就会让跑靶把拖滑块的像素当成自己那一帧（seq/slot 仍配得上，但证据对不上人）。
        # 实测代价还不止错乱：672×848 跑靶中一次 render_ms 到过 534.79 ms。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 set_strength：先 bench_stop"})
            return
        # 先全部校验、再一次性提交：这条命令里任何一个字段非法就整条不生效。
        # 原来的顺序是先把 self._strength / self._channel 提交，再校验磨皮参数；参数越界时
        # 虽然 emit error 返回了，strength 却已经被这条"没有执行"的命令改走——下一条不带
        # value 的 set_strength 会拿这个泄漏值出帧，用户看到的是"我拒绝了，画面却变了"。
        strength = _clamp_strength(p.get("value", self._strength))
        channel = self._channel
        if "channel" in p:
            if p["channel"] and p["channel"] not in self._vram.mask_names:
                emit({"event": "error", "error": f"没有掩膜通道 {p['channel']}"
                      f"（可用：{', '.join(self._vram.mask_names) or '无，先 precompute'}）"})
                return
            channel = p["channel"] or None
        # 磨皮参数：只有真变了才会重算滤波。半径直接决定 reflect pad 后的分配量
        # （积分图是 O(1)/像素但与窗口面积挂钩），没硬边界的话一个越界值就能把显存打爆，
        # 与 max_px 同一类风险。texture_radius 还要多一层：它决定线性高通的窗口，同样进分配。
        # 下界不是随手取的：eps=0 会让 `a = var/(var+eps)` 在平坦皮区算 0/0 = NaN（产品档实测
        # 402795 个子像素为 NaN）。这份 NaN 会被写进常驻缓存，而 `(1-0)*img + 0*NaN` 仍是 NaN
        # （IEEE 里 0×NaN = NaN），于是 strength=0 与解码原图差到 255 LSB —— 验收口径③
        # 整段会话被打穿。radius=0 不产 NaN，但滑块彻底空操作（实测 s=0.5 与原图 0 处不同），
        # 产品上没有任何意义，一并卡掉。texture_radius=0 同理：blur 就是原图、tex 全零，
        # “肌理保留”滑块当场变成空控件，所以协议层要 ≥1（库层仍允许 0，给对拍用）。
        params = dict(self._params)
        for k, lo, hi in (("radius", 1, 256), ("eps", 1e-6, 1.0), ("texture_radius", 1, 32),
                          ("detail_gain", 0.0, 2.0), ("mid_gain", 0.0, 2.0),
                          ("broad_gain", 0.0, 2.0)):
            if p.get(k) is None:
                continue
            try:
                v = int(p[k]) if k in ("radius", "texture_radius") else float(p[k])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                return
            if v != v:          # NaN 比大小永远是 False，不先拦就会被当成“越界”报个误导的区间错
                emit({"event": "error", "error": f"参数 {k} 不是有限数：{p[k]!r}"})
                return
            if not lo <= v <= hi:
                emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                return
            params[k] = v
        previous = self._strength, self._channel, self._params
        self._strength, self._channel, self._params = strength, channel, params
        # 出帧走与 cmd_inpaint 同一个入口：以前这里是一份手写的“render → 锁内写 shm → emit frame”，
        # 而写多份的下场已经受过（上一轮就是其中一份漏了尺寸守卫）。
        try:
            fr = self._write_current_frame("drag")
        except Exception:
            self._strength, self._channel, self._params = previous
            raise
        render_ms = fr.pop("render_ms")
        # filter_ms > 0 就是这一帧重算了滤波（参数刚变）；0.0 才是拖拽期的常态。
        emit({"event": "params_set", "strength": self._strength, "channel": self._channel,
              "render_ms": render_ms,
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              # M2-a 分层：bands_ms > 0 才是这一帧真重跑了 guided 分带。拖“匀肤/细节/肌理”
              # 三个滑块时 filter_ms 不为 0 而 bands_ms = 0，说明只重跑了逐点乘加——
              # 分带/重组两层缓存是否生效，这是唯一的直接证据。
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              # 这一帧到底复用了缓存没有：`retouched is not None` 是个恒真的说法（render 成功
              # 之后它必然非空），缓存被无声绕过时也照样报 True。只有 last_filter_ms 才由执行路径约束。
              # 名字叫 filter_cached 不叫 cached：库层字典里那条 cached 说的是“本层真重算了”，
              # 两件事共用一个键名时，字典字面量后写的会静默吃掉先写的。
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              # M2-a2：拖磨皮滑块时这一笔应当恒为 0（两份 db 结果都命中常驻）。
              # 不为 0 就是修容层把磨皮那条零推理热路径拖回了重算——两个数得分开报才能看见。
              "light_ms": round(float(self._vram.last_light_ms), 2), **self._params})
        emit(fr)

    # ------------------------------------------------------------ 消除笔（M1-4）
    def _retouch_render_args(self) -> tuple[float, str | None]:
        """Missing derived masks suspend an effect, never broaden its scope.

        Requested strength/channel stay in the recipe so reanalysis can restore them.
        Explicit unmasked API edits (channel=None) retain their existing semantics.
        """
        if getattr(self,"_creative_base",None) is not None:
            from .creative_smoothing_host import render_args
            return render_args(self)
        if self._channel and self._channel not in self._vram.mask_names:
            return 0.0, None
        return self._strength, self._channel

    def _frame_presentation(self, document_id=None, source=None, kind="edited"):
        from .frame_presentation import make
        if source is None:
            row=self._docs[self._doc_index] if 0<=self._doc_index<len(self._docs) else {}
            source=(row.get("src_w") or self._vram.w,row.get("src_h") or self._vram.h)
        return make(self._load_id if document_id is None else document_id,source,
                    self._crop_rect,self._crop_rotation,kind)

    def _write_current_frame(self, mode: str, *, original: bool = False) -> dict:
        """把当前会话渲染一帧并写 shm，返回 frame 事件字段（带 render_ms，调用方 pop）。

        set_strength / inpaint 都走这一个出口；load_image 也渲染+写 shm，但它面对的是刚刚
        新建的 shm 与一次性分段计时（shm_ms/attach_ms/first_frame_ms），所以单独一段——
        不并进来不等于可以不要守卫，尺寸不配就在这里拦一次：上一轮“三份里有一份漏守卫”
        的下场已经受过。
        """
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            raise RuntimeError(f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                               f"!= 会话 {self._vram.w}x{self._vram.h}：不许把会话尺寸的帧写进别人的槽")
        if mode != 'colour_grading_preview' or original:
            self._vram.grading_prefix_cache.invalidate()
        t0 = monotonic_ns()
        # Original viewing bypasses all layers, rather than merely setting skin strength0.
        if not original: FABRIC.sync(self); LM.sync(self); LGR.sync(self); MLR.sync(self); SBR.sync(self); OPR.sync(self); SKR.sync(self); LIPR.sync(self); BROWR.sync(self); NOSER.sync(self); EYER.sync(self); MOUTHR.sync(self); self._people_sync(); IDR.sync(self); ERR.sync(self); RCR.sync(self); SCR.sync(self); ETH.sync_current(self); PDH.sync_current(self); CGA.sync(self); SCLA.sync(self); CEA.sync(self); PCA.sync(self)
        st, channel = (0.0, None) if original else self._retouch_render_args()
        from .grading_prefix_cache import preview_context
        prefix_key = preview_context(self, mode, original)
        if prefix_key is None:
            self._vram.grading_prefix_cache.invalidate()
        def prefix_current():
            return (not getattr(self, '_colour_grading_cancelled', lambda: False)()
                    and prefix_key is not None
                    and preview_context(self, mode, original) == prefix_key)
        prefix_options = ({'prefix_key': prefix_key, 'prefix_current': prefix_current}
                          if prefix_key is not None else {})
        unapplied=not original and mode.startswith("history_") and bool(self._people_open_flags())
        if original or unapplied:
            self._vram.render_original()
        else:
            CER.render_preview(self) if CER.active(self) else PGR.render_preview(self) if PGR.active(self) else SKR.render_proxy(self,lambda:self._vram.render(st, channel=channel, **self._params, **prefix_options),
                             allow_suspended=mode not in ("preset","batch","sky_replacement"))
        render_ms = (monotonic_ns() - t0) / 1e6
        with self._wlock:
            publication = getattr(self, "_colour_editor_publication", None) or getattr(self, "_photo_grain_publication", None) or getattr(self, "_photo_detail_publication", None) or getattr(self, "_primary_calibration_publication", None) or getattr(self, "_selective_colour_publication", None) or getattr(self, "_colour_grading_publication", None) or getattr(self, "_custom_lut_publication", None) or getattr(self, "_extended_tone_publication", None)
            write = lambda: self.shm.write_frame(self._vram.read_back(), presentation=self._frame_presentation(kind="original" if original or unapplied else "edited"))
            seq, t_emit, slot = publication.publish(write) if publication is not None else write()
        return {"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                "w": self.shm.w, "h": self.shm.h, "mode": mode, "render_ms": round(render_ms, 2),
                "strength": st, "bytes_effect_recovery": self._vram.effect_recovery_resident_bytes(),
                **({"sky_replacement_suspended":None,"suspended_effects":[],"display_quality":"original"} if original else {**SKR.proxy_flags(self),**(self._people_open_flags() if unapplied else {})})}

    def cmd_compare(self, p: dict):
        """临时显示完整解码原图，绕过全部编辑；松手恢复完整配方。

        不改参数、不清缓存、不进撤销栈。strength=0 仍会保留曝光/LUT/修补等层，
        因此不能冒充原图；本入口直接打包原始工作空间源张量。
        """
        # 参数校验排在最前（与 cmd_history 同一顺序）：一条写坏的命令应当被报成
        # "写坏了"，而不是被状态守卫抢先报成"还没导进来"——后者会把真正的笔误藏起来。
        unknown = set(p) - {"cmd", "on", "capture_id"}
        if unknown:
            emit({"event": "error", "error": f"compare 收到不认识的参数：{sorted(unknown)}"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 compare：先 bench_stop"})
            return
        if "on" in p and not isinstance(p["on"], bool):
            emit({"event": "error", "error": "compare on 必须是 boolean"})
            return
        capture_id = p.get("capture_id")
        if capture_id is not None and (not isinstance(capture_id, str) or not 1 <= len(capture_id) <= 128):
            emit({"event": "error", "error": "compare capture_id 必须是 1–128 字符的字符串"})
            return
        on = p.get("on", True)
        fr = self._write_current_frame("compare", original=on)
        fr.update(document_id=self._load_id,shm_instance=self.shm.instance_id.hex(),seq_id=str(fr["seq"]))
        fr["capture_id"] = capture_id
        fr["doc"] = self._doc_path
        fr["view"] = "original" if on else "edited"
        fr.pop("render_ms")          # 与 set_strength 同一口径：这一笔随 params_set 报，不塞进 frame
        emit(fr)

    def cmd_inpaint(self, p: dict):
        """消除笔：一次事件（松手）算一次修补；拖滑块期间不重算也不重上传。

        与 M1-3c 同一原则：一次性成本与逐帧成本分开报。这里的一次性成本 =
        RLE 解码 + 羽化 + 裁块修补 + 滤波重放；之后的拖动只读现成的 repair_base。
        """
        action = p.get("action", "add")
        if action not in ("add", "undo", "redo", "clear"):
            emit({"event": "error", "error": f"未知 inpaint action: {action}"
                  f"（可用：add/undo/redo/clear）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            # 与 set_strength 同一条守卫：跑靶线程在写 frame_gpu，这里也写同一块
            emit({"event": "error", "error": "跑靶进行中，拒绝 inpaint：先 bench_stop"})
            return
        t_start = monotonic_ns()
        info_add = {}
        if action == "add":
            # 先全部校验、再一次性提交（与 cmd_set_strength 同一条铁律）：
            # 被拒绝的命令必须整条不留痕，不能“图层加了一半、参数改了”那种中间态。
            import numpy as np

            from .ops.inpaint import feather_np, mask_from_rle

            rle = p.get("rle")
            if not isinstance(rle, list):
                emit({"event": "error", "error": "inpaint add 缺 rle：应为 [[y,x,len,value255], …]"
                      "（从代理帧坐标采集，尺寸就是 shm_ready 的 w/h）"})
                return
            if len(rle) == 0:
                emit({"event": "error", "error": "rle 为空：这一笔一个像素也没盖到，不该发这条命令"})
                return
            h, w = self._vram.h, self._vram.w
            try:
                hard = mask_from_rle(rle, h, w)
            except (ValueError, TypeError) as e:
                emit({"event": "error", "error": f"rle 非法，整条拒绝：{e}"})
                return
            feather = int(p.get("feather", 2))
            if not 0 <= feather <= 8:
                emit({"event": "error", "error": f"feather={feather} 超出范围 [0, 8]"})
                return
            params = dict(DEFAULT_REPAIR)
            for k, lo, hi, cast in (("smooth_iters", 0, 4, int), ("refine_iters", 0, 32, int),
                                    ("kappa", 1e-3, 1.0, float), ("pad", 0, 256, int),
                                    ("grow", 1.0, 8.0, float)):
                if p.get(k) is None:
                    continue
                try:
                    v = cast(p[k])
                except (TypeError, ValueError):
                    emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                    return
                if not lo <= v <= hi:
                    emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                    return
                params[k] = v
            backend = p.get("backend", "builtin")
            if backend != "builtin":
                # 不许静默降级（与 face.MediaPipeFace 同一条规矩）：请求真模型而权重不在，
                # 就报错说清缺什么，绝不“退成内置扩散然后报一个修补成功”。
                # （lama 在 ops 包里：上一版写成 `from . import lama`，这条守卫自己先报
                # ImportError，文案全丢——守卫也要能被测到才算守卫。）
                from .ops import lama

                emit({"event": "error", "error": lama.missing_reason(backend)})
                return
            t_dec = monotonic_ns()
            soft = feather_np(hard, feather) if feather else (hard.astype(np.float32))
            weight = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
            if int((weight > 0).sum()) == 0:
                emit({"event": "error", "error": "羽化后覆盖度归零：画笔太小或 feather 与坐标不匹配"
                      "（会话为代理帧尺寸，得用代理帧坐标而不是原图坐标）"})
                return
            decode_ms = (monotonic_ns() - t_dec) / 1e6
            # 号只在提交成功后占：add_repair 内部现在“全算完才写回”，真失败时图层
            # 一笔也不会多出来，把自增放在前面会白白跳号
            op = RepairOp(op_id=self._op_seq + 1, weight=weight, params=params)
            info = self._vram.add_repair(op)
            self._op_seq = op.op_id
            info_add = {"op_id": op.op_id, "decode_ms": round(decode_ms, 2),
                        "backend": backend, "feather": feather, "params": dict(params),
                        "rle_runs": len(rle)}
        elif action == "undo":
            info = self._vram.undo_repair()
            if info is None:
                emit({"event": "error", "error": "没有可撤销的消除笔操作"})
                return
        elif action == "redo":
            info = self._vram.redo_repair()
            if info is None:
                emit({"event": "error", "error": "没有可重做的消除笔操作"})
                return
        else:
            info = self._vram.clear_repair()
        # 引擎侧那份列表必须跟着会话走：不同步的话下一次换设备会重放出旧图层
        self._repair_ops = list(self._vram.repair_ops)
        self._redo_ops = list(self._vram.redo_ops)
        fr = self._write_current_frame("repair")
        render_ms = fr.pop("render_ms")
        emit({"event": "inpaint_done", "action": action, **info, **info_add,
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              "repair_ms": info["repair_ms"], "render_ms": render_ms,
              "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
              "device": str(self._vram.device), "strength": self._strength})
        emit(fr)

    def _light_params_or_reject(self, p: dict):
        """从命令里取修容层参数，全部校验通过才返回；失败时自己发 error 并返 None。

        为什么单独拆出来：add 与 params 两条臂都得能带 exposure/radius。上一版只在
        params 里处理，add 带了就直接**静默忽略**——手工跑一条 add 带 radius=6 时
        上报里仍是默认的 24，而 exposure 默认值恰好也是 0.6，整个事件看不出任何异常。
        静默吞掉一个参数比报错难查十倍。
        """
        got = {}
        for k, lo, hi in (("exposure", -DB_EXPOSURE_LIMIT, DB_EXPOSURE_LIMIT),
                          ("radius", 0, 256)):
            if p.get(k) is None:
                continue
            try:
                v = float(p[k]) if k == "exposure" else int(p[k])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                return None
            if not v == v or abs(v) == float("inf"):
                emit({"event": "error", "error": f"参数 {k} 不是有限数：{p[k]!r}"})
                return None
            if not lo <= v <= hi:
                emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                return None
            got[k] = v
        return got

    def cmd_light(self, p: dict):
        """修容笔（M2-a2）：一次事件（松手/改完参数）算一次场；拖磨皮滑块期间不重算。

        与消除笔同一套事件调度、同一条铁律：先全量校验、后一次性提交，被拒绝的命令
        整条不留痕（不能“图层加了一笔、参数改了、场还是旧的”那种中间态）。
        """
        action = p.get("action", "add")
        if action not in ("add", "undo", "redo", "clear", "params"):
            emit({"event": "error", "error": f"未知 light action: {action}"
                  f"（可用：add/undo/redo/clear/params）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 light：先 bench_stop"})
            return
        t_start = monotonic_ns()
        info_add: dict = {}
        if action == "params":
            # 参数也得“先校验后写”：一半一半会留下一张用旧曝光算出来、但上报写着新曝光的帧
            got = self._light_params_or_reject(p)
            if got is None:
                return
            if not got:
                emit({"event": "error", "error": "light params 什么也没给：至少要有 exposure 或 radius"})
                return
            self._light = dict(self._light, **got)
            info = self._vram.set_light_params(self._light["exposure"], self._light["radius"])
            info_add = {"params": dict(self._light)}
        elif action == "add":
            import numpy as np

            from .ops.inpaint import feather_np, mask_from_rle

            rle = p.get("rle")
            if not isinstance(rle, list) or not rle:
                emit({"event": "error", "error": "light add 缺 rle 或 rle 为空："
                      "应为 [[y,x,len,value255], …]，从代理帧坐标采集"})
                return
            h, w = self._vram.h, self._vram.w
            try:
                hard = mask_from_rle(rle, h, w)
            except (ValueError, TypeError) as e:
                emit({"event": "error", "error": f"rle 非法，整条拒绝：{e}"})
                return
            try:
                sign = int(p.get("sign", 1))
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"sign 非法：{p.get('sign')!r}（需 +1 减淡 / -1 加深）"})
                return
            if sign not in (-1, 1):
                emit({"event": "error", "error": f"sign={sign} 非法：只能是 +1（减淡）或 -1（加深）"})
                return
            feather = int(p.get("feather", 2))
            if not 0 <= feather <= 8:
                emit({"event": "error", "error": f"feather={feather} 超出范围 [0, 8]"})
                return
            t_dec = monotonic_ns()
            soft = feather_np(hard, feather) if feather else hard.astype(np.float32)
            weight = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
            if int((weight > 0).sum()) == 0:
                emit({"event": "error", "error": "羽化后覆盖度归零：画笔太小或坐标不匹配"
                      "（会话为代理帧尺寸，得用代理帧坐标而不是原图坐标）"})
                return
            decode_ms = (monotonic_ns() - t_dec) / 1e6
            # 带不带参数都得过同一道校验：静默忽略比拒绝坏得多
            got = self._light_params_or_reject(p)
            if got is None:
                return
            op = LightOp(op_id=self._op_seq + 1, weight=weight, sign=sign)
            prev_light = dict(self._light)
            if got:
                # 参数先于建层：两者在同一条事件里，提交后帧与上报必须同时是新参数的
                self._light = dict(self._light, **got)
                self._vram.set_light_params(self._light["exposure"], self._light["radius"])
            try:
                info = self._vram.add_light(op)
            except Exception as e:
                # 回滚必须成对。上一版只 except ValueError 且不回滚参数：任何
                # RuntimeError（先 load_rgb_u8）、非有限场、显存 OOM 都会留下“参数已是新的、
                # 图层一笔没加、事件一条没发”的半应用状态——上报里曝光变了而画面按旧曝光
                # 渲染，Rust 侧 status.light 还停在上一条 payload。cmd_set_strength 已为同一个
                # 形状付过钱：“先全量校验、后一次性提交”不是注释，得真的回得去。
                self._light = prev_light
                try:
                    self._vram.set_light_params(prev_light["exposure"], prev_light["radius"])
                except Exception:      # 回滚本身再抛就得当场说清，不能留个“看起来已回滚”的状态
                    emit({"event": "engine_warn",
                          "warn": f"修容回滚失败，参数层已不可信，请重新导图：{type(e).__name__}"})
                emit({"event": "error",
                      "error": f"修容被拒，参数一并回滚（{type(e).__name__}）：{e}"})
                return
            self._op_seq = op.op_id
            info_add = {"op_id": op.op_id, "sign": sign, "decode_ms": round(decode_ms, 2),
                        "rle_runs": len(rle), "feather": feather, "params": dict(self._light)}
        elif action == "undo":
            info = self._vram.undo_light()
            if info is None:
                emit({"event": "error", "error": "没有可撤销的修容笔"})
                return
        elif action == "redo":
            info = self._vram.redo_light()
            if info is None:
                emit({"event": "error", "error": "没有可重做的修容笔"})
                return
        else:
            info = self._vram.clear_light()
        # 引擎侧那份列表必须跟着会话走：不同步的话下一次换设备会重放出旧图层
        self._light_ops = list(self._vram.light_ops)
        self._light_redo = list(self._vram.light_redo)
        fr = self._write_current_frame("light")
        render_ms = fr.pop("render_ms")
        # 显存账单在渲染之后才算：建层那一刻两份 db 结果还是空的，在那里报会少算
        # 两个产品档各 6.5 MiB——“零重算”换来的显存代价藏不得
        info["bytes_light"] = self._vram.light_resident_bytes()
        emit({"event": "light_done", "action": action, **info, **info_add,
              "light_ms": round(float(self._vram.last_light_ms), 2),
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              "render_ms": render_ms,
              "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
              "device": str(self._vram.device), "strength": self._strength})
        emit(fr)

    # -------------------------------------------------- 多人图的分人编辑（PORTRAIT-003）
    # 人工账的三条动作（PORTRAIT-006）。名单要进 ready 上报，前端自己刻一份就是
    # 下一轮加动作时漏改的那一处（与 DEFORM_ACTIONS 同一条教训）
    FACE_ACTIONS = ("list", "select", "disable", "enable", "add", "remove")
    # 按盒认人时「算同一个人」的 IoU 下限。0.5 不是审美数字：两张相邻的脸在同一张
    # 图上的盒通常交不到 0.5，而同一个人被两个后端/两档代理框出来的盒交得到 0.7 以上
    # （实测见 ADR-0017）。取中间值 0.5，认不过就明说认不过，不做二次猜测。
    MANUAL_IOU_MIN = 0.5

    @staticmethod
    def _manual_box(v):
        """把一条人工账归一成 4 元归一化盒；不成形就返 None（调用方丢，不留残框）。"""
        try:
            if v is None or len(v) != 4:
                return None
            box = tuple(round(float(x), 5) for x in v)
        except (TypeError, ValueError):
            return None
        if not all(0.0 <= x <= 1.0 for x in box) or not (box[0] < box[2] and box[1] < box[3]):
            return None
        return box

    def _manual_boxes(self, key: str) -> list[tuple]:
        ledger = self._face_manual or {}
        return [b for b in (self._manual_box(v) for v in (ledger.get(key) or [])) if b is not None]

    def _match_face_by_iou(self, pc, box):
        """在一份名单里按 **IoU** 找回那一个人；认不出返 None。

        与 `_match_face_by_box`（容差 1e-3 的逐位比）分两处是有意的：选型要的是
        「就是这一轮那一张」，人工账要的是「还是那个人」——后者在换后端/换模型时盒会
        漂，逐位比等于宣布人工纠正只在同一次推理内有效，而冻结件的 when 写的是
        「后台重检测**或更换检测模型**」。
        """
        from .face import box_iou

        want = self._manual_box(box)
        if pc is None or want is None:
            return None
        best_i, best = None, 0.0
        for f in pc.faces():
            iou = box_iou(f["box"], want)
            if iou > best:
                best_i, best = int(f["index"]), iou
        return best_i if best >= self.MANUAL_IOU_MIN else None

    def _disabled_indices(self, pc=None) -> set:
        pc = self._precompute if pc is None else pc
        out = set()
        if pc is None:
            return out
        for b in self._manual_boxes("disabled"):
            i = self._match_face_by_iou(pc, b)
            if i is not None:
                out.add(i)
        return out

    def _face_state(self) -> dict:
        """「现在在改哪一张 / 名单上有谁 / 人工账盖在上面之后剩谁」那一格。

        名单只从分析结果算（单一出处），人工账只从这里叠上去（也是单一出处）：
        UI 的 chip、deform/enhance 的放行、验收的判据都读这一份，各自拼一遍就会
        出现“面板能点而引擎拒”那种无响应控件（DoD §3 明确禁止的那件事）。
        """
        from .face import SCOPE_MAX_FACES, box_iou

        if self._people_managed():
            from .people_face_compat import report
            return report(self)
        pc = self._precompute
        faces = pc.faces() if pc is not None else []
        disabled_idx = self._disabled_indices(pc)
        for f in faces:
            f["disabled"] = bool(int(f["index"]) in disabled_idx)
        enabled = [int(f["index"]) for f in faces if not f["disabled"]]
        detected_multi = bool(pc is not None and int(getattr(pc, "num_faces", 1)) > 1)
        ledger_disabled = self._manual_boxes("disabled")
        ledger_added = self._manual_boxes("added")
        # 账上认不回的条目：它们**留在账上**（丢掉就是一次静默恢复），但要如实报出去
        stale_disabled = [list(b) for b in ledger_disabled
                          if self._match_face_by_iou(pc, b) is None]
        lost_added = [list(b) for b in ledger_added
                      if pc is not None and self._match_face_by_iou(pc, b) is None]
        # 「这次检测要新增谁」：名单里既没被禁用、也不在任何一条人工账里的那些——
        # 冻结件的“变化可预览”要的就是这份账，而不是让用户自己对着 chip 数
        fresh_faces = [int(f["index"]) for f in faces
                       if not f["disabled"] and not any(box_iou(f["box"], b) >= self.MANUAL_IOU_MIN
                                                         for b in ledger_disabled + ledger_added)]
        return {"index": int(self._face_index), "explicit": bool(self._face_explicit),
                "box": (None if self._face_box is None
                        else [round(float(v), 5) for v in self._face_box]),
                "num_faces": len(faces), "faces": faces,
                "enabled": enabled, "disabled_count": len(faces) - len(enabled),
                # 名单上有几个人 vs 这一轮**探到**几张脸：人工补的那一张不是探出来的。
                # 混成一格就会把"用户框的一位"说成"模型找到的一位"——那是谎报能力面
                "probed": len(faces) - len([f for f in faces if f.get("manual")]),
                # 放行判据只写这一处：还剩两个以上可编辑的人而没显式选过 = 挡住（SCOPE-001），
                # 选过 = 能改那一张（PORTRAIT-003）。用户关掉一只误检后只剩一个人时放行——
                # 那一步是**人做的排除**，不是引擎替人选
                "blocked": bool(len(enabled) > 1 and not bool(self._face_explicit)),
                # 「这一轮分析是不是多人图」是原始事实，不随人工账翻牌（SCOPE-001 的 P0
                # 判据钉的就是这一格；test_face_select 与端到端两处都在读它）
                "scope_block": "multi_face" if detected_multi else None,
                "max_faces_probed": SCOPE_MAX_FACES,
                "manual": {"disabled": [list(b) for b in ledger_disabled],
                           "added": [list(b) for b in ledger_added],
                           "stale": stale_disabled, "lost": lost_added,
                           "new_faces": fresh_faces,
                           # 冻结件 then 那句「变化可预览」的落点：重检测之后这一格随
                           # precompute_ready 一起报出去，UI 不用自己比对两轮名单
                           "preview": (
                               f"保留 {len(ledger_disabled) - len(stale_disabled)} 处禁用、"
                               f"{len(ledger_added) - len(lost_added)} 处人工补的脸"
                               + (f"，认不回 {len(stale_disabled)} 处禁用" if stale_disabled else "")
                               + (f"，{len(lost_added)} 框这一轮没找回" if lost_added else "")
                               + (f"，本轮新增 {len(fresh_faces)} 张无人工记录的脸"
                                  if fresh_faces else ""))}}

    @staticmethod
    def _match_face_by_box(pc, box) -> int | None:
        """在一份分析结果里按**脸盒**找回那一张脸；找不回来返 None。

        容差 1e-3（归一化坐标）是给同一次推理的重算余量：同一张图同一档代理跑
        两次检测，点位应逐字节一致；真漂过这一档就不是“同一个人”了，宁可不认。
        """
        if box is None:
            return None
        want = [round(float(v), 5) for v in box]
        for f in pc.faces():
            if f["box"] and max(abs(a - b) for a, b in zip(f["box"], want)) < 1e-3:
                return int(f["index"])
        return None

    def _face_guard(self) -> tuple[bool, str]:
        """单脸作用域的操作现在能不能放行（唯一出处，deform 与 enhance 两条臂都读它）。

        以前两边各自拼了一遍“多人且没选定”，于是加进人工禁用之后两边的口径会分家：
        账上关掉一只误检的人，会看到面板能点而引擎仍按“探到两张”拒（DoD §3 禁止的那件
        事）。判据按**还剩几个可编辑的人**算：那一步排除是人做的，不是引擎替人选。
        """
        st = self._face_state()
        if not st["blocked"]:
            return False, ""
        from .face import SCOPE_MAX_FACES
        return True, (
            f"名单上 {st['num_faces']} 个人、可编辑的有 {len(st['enabled'])} 个"
            f"（这一轮探到 {st['probed']} 张脸，检测上限探 {SCOPE_MAX_FACES} 张，"
            f"人工关掉 {st['disabled_count']} 只）：面部重塑与眼牙"
            "增强需要且仅需要一张可用人脸，本版本不在多人照片里替你选哪一张（SCOPE-001）；"
            f"要改谁先用 `face select` 显式选定那一张（名单：{st['faces']}，PORTRAIT-003），"
            "或用 `face disable` 关掉误检那一只（PORTRAIT-006）；"
            "全图调色、曝光/白平衡、裁剪与磨皮仍可用")

    def _refresh_frame_after_drop(self, tag: str) -> None:
        """把一层放下之后补一帧：生效值清了而帧没重画，屏幕上还是刚才那张改过的脸。

        这不是理论问题。`_rebuild_deform_for_landmarks` 的两条 invalidate 臂原来只
        `clear_deform()` 就 return，只有在**建新层并点亮**时才补帧；于是“重分析认不回
        上次选定那一张”之后，事件报 `lit=false` 而屏幕仍是瘦过的脸——报表与画面双向
        错配。PORTRAIT-006 的逐字节判据（关掉的那一只在重检测后的那一帧上不得重新出现）
        抓的正是这个形状，所以三条放下臂现在都走这里。
        """
        if self.shm is None or self._vram is None:
            return
        if (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            return                       # 会话尺寸变了：这一帧本来就不该由本命令写
        try:
            fr = self._write_current_frame(tag)
            fr.pop("render_ms", None)
            emit(fr)
        except Exception as e:                        # noqa: BLE001
            emit({"event": "engine_warn", "warn": f"放下层之后补帧失败（{tag}）：{e}"})

    def _drop_face_selection(self, why: str, *, write_frame: bool = True) -> None:
        """放下「正在改谁」与挂在那个人身上的两层的**生效值**，保留「用户改过什么」。

        与 `_preserve_face_choice` 里那条失败路径同一口径：清的是会话里那一层，而
        全人物默认与逐张覆盖按脸盒留着——用户把那个人选回来时还得接得回来。
        """
        amounts = dict(self._deform["amounts"])
        # 两层里任何一层当时在画面上亮着，放下之后都得补一帧（一次补够，不各补各的）
        lit_before = bool(self._vram is not None
                          and (self._vram.has_deform() or self._vram.has_enhance()))
        if self._deform["built"]:
            self._vram.clear_deform()
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        self._deform_defer = False
        self._face_index = 0
        self._face_box = None
        self._face_explicit = False
        self._emit_deform_state("invalidate", reason=why, dropped_amounts=amounts)
        if self._enhance_intent() or self._enhance["built"]:
            # 眼牙那一层认的是脸盒：选型一放下，`_rehang_enhance` 就会因为认不出
            # “这一层挂在谁身上”而整场放下（不拿 A 的参数静默服务 B）
            self._rehang_enhance(self._precompute, replayed_for="face_selection_dropped",
                                 write_frame=False)
        if lit_before and write_frame:
            self._refresh_frame_after_drop("face_selection_dropped")

    def _reapply_face_manual(self, pc, *, backend=None, tag: str = "precompute"):
        """把人工账重贴到这一轮的名单上（PORTRAIT-006）。返回 (新名单, 账)。

        三条判据直接来自冻结件那句「人工纠正保留，变化可预览；不静默恢复已禁用误检」：

        · **禁用按 IoU 认**而不是逐位相等：`when` 那一栏写的是“后台重检测**或更换检测
          模型**”，换模型后脸盒会漂（template→mediapipe 能漂出几十个百分点），逐位相等
          等于宣布人工纠正只在同一次推理内有效；
        · 认不回的条目**留在账上**并标 stale：悄悄丢掉用户关过的那一只，下一轮检测它
          就会以“没被禁用”的身份重新出现在名单里——那正是“静默恢复”；
        · 人工补的那一张要重新从**框**里取一次点位（换了后端就按新后端取）。取不到就
          在账里明说“这一框这一轮没找回”，不拿旧点位、更不拿占位点位续命：那层的控制点
          不在那个脸上，而屏幕上看不出来。
        """
        from . import face as face_mod

        kept, lost = [], []
        for rect in self._manual_boxes("added"):
            if self._match_face_by_iou(pc, rect) is not None:
                # 这一轮模型自己探到了这个人：人工框的使命完成了，账仍留着（用户改过的
                # 判断不因模型进步而消失），但不再重复 append 一张同脸
                kept.append({"rect": list(rect), "state": "detected"})
                continue
            if backend is None or getattr(self, "_src_rgb", None) is None:
                lost.append({"rect": list(rect),
                             "reason": "这一轮没有可重跑的区域检测后端/代理帧：这一框的人工脸"
                                       "没找回，账仍保留"})
                continue
            try:
                lm, info = face_mod.detect_region(backend, CDH.analysis_rgb(self), rect)
                pc = pc.with_manual_face(lm)
            except Exception as e:                        # noqa: BLE001
                lost.append({"rect": list(rect),
                             "reason": f"{type(e).__name__}: {e}"})
                continue
            kept.append({"rect": list(rect), "state": "readded", "iou": info["iou"],
                         "box": info["box"], "landmark_backend": info["backend"]})
        ledger = {"kept": kept, "lost": lost}
        if kept or lost:
            # 这里只报账本身（“哪一框找回了、哪一框没找回”）：完整的名单状态由随后的
            # precompute_ready 报——那会儿 `self._precompute` 已经是新那一份，现在报只会
            # 把旧名单当新名单发出去
            emit({"event": "face_manual", "action": "reapply", "tag": tag,
                  "kept": kept, "lost": lost})
        return pc, ledger

    def _replay_face_view(self) -> None:
        """把当前这份 `_precompute` 重新指到选定那一张上（认不回脸就退回未选定）。

        先认脸盒、后认 index：index 只在“那一次分析”里有意义，而重放发生在
        历史回滚/选型回填之后，那两侧的名单未必是同一轮跑出来的。
        """
        pc = self._precompute
        if pc is None:
            return
        pool = pc.all_landmarks or [pc.landmarks]
        idx = self._match_face_by_box(pc, self._face_box)
        if idx is None:
            idx = int(self._face_index or 0)
        if idx == pc.face_index:
            return
        if not 0 <= idx < len(pool):
            emit({"event": "engine_warn",
                  "warn": f"选型 index {idx} 在这一次分析里没有对应的人脸（探到 {len(pool)} 张）："
                          "退回未选定状态——要改谁请重新点选，引擎不替你猜那一张"})
            self._face_index = 0
            self._face_box = None
            self._face_explicit = False
            return
        try:
            view = pc.select_face(idx)
        except ValueError as e:
            emit({"event": "engine_warn", "warn": f"选型重放失败，保持上一次的关键点：{e}"})
            return
        self._precompute = view
        self._face_index = int(view.face_index)
        self._face_box = tuple(float(v) for v in (view.face_box or ())) or None

    def _preserve_face_choice(self, pc):
        """新一轮分析后尽量保住“用户上次显式选的那一张”，对不上就退回未选定。

        为什么按**脸盒**认而不是按 index 认：检测器的返回顺序不是人能预期的（这一点
        写在 face.py 的注释里），拿旧序号对新名单就是一次静默选型。对不上而旧形变层还
        常驻时，只能整层清掉：留着就是把“刚才瘦的那张脸”悄悄换成另一张。
        """
        old = self._precompute
        was_explicit = bool(self._face_explicit)
        pool = pc.all_landmarks or [pc.landmarks]
        # 人工账已经叠在这份名单上了（`_reapply_face_manual` 跑在本方法之前），所以这里
        # 的“还剩谁”是算过用户关掉哪几只之后的结果
        disabled = self._disabled_indices(pc)
        enabled = [i for i in range(len(pool)) if i not in disabled]
        if len(pool) <= 1:
            # 只有一张：没什么可选，脸盒留着当“这同一张”的身份（下一轮又变多人时能认回来）
            if enabled:
                self._face_index = 0
                self._face_box = tuple(float(v) for v in (pc.face_box or ())) or None
            else:
                # 而这一张已被用户关掉（“这不是脸”）：它不能再服务任何人。放下选型与生效值，
                # 而**不改那份账**——账上是用户说过的话，不是引擎没听见的事
                self._drop_face_selection(
                    "这一轮探到的那一张已被人工禁用（误检）：会话里的形变与眼牙层已放下，"
                    "全人物默认与逐张覆盖按脸盒留着，`face enable` 恢复后即可接回")
            return pc
        hit = self._match_face_by_box(pc, self._face_box) if old is not None else None
        if hit is not None and hit in disabled:
            # 上次选定那一张现在是「用户说不是脸」的那一只：认回来也不能继续服务它。
            # 禁用是一次人的判断，优先级高于一次选型
            hit = None
        if hit is None and old is None and was_explicit:
            # 重开工程那一条路：本会话里没有“上一轮”可认，而名单就是这张图刚跑出来的
            # 那一轮——按存下来的 index 认，并对上脸盒才算数（对不上就照旧走下面的退回）
            if 0 <= int(self._face_index or 0) < len(pool):
                cand = [round(float(v), 5) for v in (pc.faces()[int(self._face_index)]["box"] or ())]
                want = [round(float(v), 5) for v in (self._face_box or ())]
                if want and cand and max(abs(a - b) for a, b in zip(cand, want)) < 1e-3:
                    hit = int(self._face_index)
        if was_explicit and hit is not None:
            view = pc.select_face(hit)
            self._face_index = hit
            self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
            return view
        self._face_index = 0
        self._face_box = None
        self._face_explicit = False
        if was_explicit and (self._deform["built"] or self._deform_defer):
            amounts = dict(self._deform["amounts"])
            was_lit = bool(self._vram.has_deform())
            self._vram.clear_deform()
            self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
            # 待重挂的那一层也一起吃掉：留着它就是一次静默选型——下一次分析会把
            # “刚才那一张的形变值”按新名单里不知道哪一张重建出来。
            # 但**两份层级不能跟着抹**（PORTRAIT-004）：覆盖挂在脸盒上，而脸盒是这一轮
            # 名单里可能再次出现的东西（同图重分析），抹掉就是把用户的活儿按引擎认不回
            # 人这件事烧掉。放下的是“当前生效值”，不是“用户改过什么”
            self._deform_defer = False
            self._emit_deform_state("invalidate",
                                    reason="重新分析后没能认出上次显式选定的那一张脸（多人图）："
                                           "会话里的形变已放下，不拿旧序号去服务另一张脸；"
                                           "全人物默认与逐张覆盖仍按脸盒留着，重新 `face select` "
                                           "选定那一张就接得回来",
                                    dropped_amounts=amounts)
            if was_lit:
                # 层放下了就必须补一帧：不然屏幕上还挂着上一次那一张的形变，而事件已经
                # 报 lit=false（详见 _refresh_frame_after_drop）
                self._refresh_frame_after_drop("face_invalidate")
        # 人工账把名单削到只剩一个可编辑的人：这时候「改谁」已经由用户那次排除决定，
        # 直接指到那一张，而不是要求他对着一份只剩一格的名单再点一次。这一步要明说，
        # 因为它确实是一次选型（PORTRAIT-006），只是主意是人不是引擎
        if len(enabled) == 1:
            view = pc.select_face(enabled[0])
            self._face_index = enabled[0]
            self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
            self._face_explicit = True
            emit({"event": "engine_warn",
                  "warn": f"人工禁用之后只剩一个可编辑的人（index {enabled[0]}）："
                          "已把这一张指为当前编辑对象（PORTRAIT-006：这一步是人做的排除）"})
            return view
        return pc

    def cmd_face(self, p: dict):
        """多人图里选定“这次改哪一张脸”（PORTRAIT-003）。

        为什么这是一条引擎命令而不是 UI 的事：SCOPE-001 挡的就是“引擎替你选了一张脸”，
        那放行的凭据必须是**用户的一次显式选择**，而这份选择要进文档状态、进撤销栈、
        进出片口径——全在引擎侧。前端只画 chip 与发 index。
        """
        if self._people_managed():
            from .people_face_compat import apply
            return apply(self,p,emit)
        action = p.get("action", "list")
        if action not in self.FACE_ACTIONS:
            emit({"event": "error",
                  "error": f"未知 face action: {action}（可用：{'/'.join(self.FACE_ACTIONS)}）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        pc = self._precompute
        if pc is None:
            emit({"event": "error", "error":
                  "face 需要先 precompute：没有 478 点关键点就没有可列的人脸名单。"
                  "名单不许前端自己猜：猜出来的 chip 数与引擎能服务的张数一旦不一致，"
                  "“选了而没生效”就再也查不清是谁的错"})
            return
        if action == "list":
            st = self._face_state()
            # 同一份状态两种形状：平铺（历史形状，宿主与用例都读得到）与嵌套（宿主那一个
            # 槽位多源汇入，靠 `face` 这一格认出对象）。只算一次，不写两份。
            emit({"event": "face_list", "t_face_ms": 0.0, **st, "face": st})
            return
        if action in ("disable", "enable", "add", "remove"):
            # 人工账的四条动作（PORTRAIT-006）。分出去是因为它们改的是**名单与账**，
            # 而 select 改的是「当前视图」——两条路径的失败回滚面不一样，混在一个函数里
            # 迟早出现「账改了而视图没改」那一族错配
            self._face_manual_action(action, p)
            return
        raw = p.get("index")
        faces = pc.faces()
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            emit({"event": "error", "error": f"face index 要是整数，得到 {raw!r}"})
            return
        idx = int(raw)
        if idx != raw or not 0 <= idx < len(faces):
            emit({"event": "error", "error":
                  f"face index {raw} 不在名单里（这一轮探到 {len(faces)} 张脸，"
                  f"可选 0…{max(0, len(faces) - 1)}）"})
            return
        if idx in self._disabled_indices(pc):
            # 用户说过「这不是脸」，引擎就不服务那一张（PORTRAIT-006）。要改主意先 enable：
            # 让 select 顺手把禁用解掉，等于一次点击推翻另一条人工判断，两笔账就分不清了
            emit({"event": "error", "error":
                  f"第 {idx} 张已被人工禁用（误检）：先用 `face enable` 恢复再选定"})
            return
        try:
            view = pc.select_face(idx)
        except ValueError as e:
            emit({"event": "error", "error": f"选型被拒，状态原样保留：{e}"})
            return
        prev_pc, prev_index = self._precompute, self._face_index
        prev_box, prev_explicit = self._face_box, self._face_explicit
        self._precompute = view
        self._face_index = idx
        self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
        self._face_explicit = True
        if self._deform_intent():
            # 已常驻的形变层必须跟着换人：留着旧那份，报的是“选中的人”而画的是
            # “上次那一张”的脸——双向错配里最难复查的一族。
            # 待重挂的那一份也一样：不跟着选型重建，下一次补上的就是旧那一张的几何。
            # 第三种形状只有层级（PORTRAIT-004）：`_preserve_face_choice` 认不回上次
            # 选定那一张时放下的是生效值，而默认与逐张覆盖按脸盒留着——用户现在把那张
            # 脸选回来了，就必须在这里接上，否则“覆盖跟着人回来”要用户再摸一次滑块才算
            # 生效，那是一条按了没反应的控件
            try:
                self._rebuild_deform_for_landmarks(view)
            except Exception as e:
                (self._precompute, self._face_index, self._face_box, self._face_explicit) = \
                    (prev_pc, prev_index, prev_box, prev_explicit)
                emit({"event": "error", "error":
                      f"换人失败({type(e).__name__})：{e}，已退回上一份选型"})
                return
        # 眼牙层（PORTRAIT-009）也要跟着换人走，而且它认的是**脸盒**：这一层的掩膜是从
        # 那一张脸的 478 点画的，把 A 的美白静默涂到 B 身上正是 SCOPE-001 拦的那件事。
        # 认不回上次那一张就整场放下并写明原因（参数留着，因为它属于“用户改过什么”）。
        # 排在选型提交之后：失败路径已经在上面 return 了，这里看到的必须是新那一张。
        if self._enhance_intent() or self._enhance["built"]:
            self._rehang_enhance(view, replayed_for="face_view")
        if BROWS.active(self._brow_shape) or NOSES.active(self._nose_shape) or EYES.active(self._eye_shape) or MOUTHS.active(self._mouth_shape):
            emit(self._write_current_frame("brow_shape_face_changed"))
        fst = self._face_state()
        emit({"event": "face_selected", "action": "select", "requested_index": idx,
              # 没点火时选型不该改动画面：这一格给端到端用例当判据（“选人不等于调图”）
              "frame_changed": bool(self._deform["built"]),
              # 平铺 + 嵌套同一份：嵌套那一份是给宿主 `note_face()` 认对象用的（它与
              # precompute_ready、doc_state 汇进同一个槽位），平铺那一份是历史形状。
              **fst, "face": fst})

    def _settle_face_layers(self, replayed_for: str) -> None:
        """人工账改动之后，把两层按当前名单重新落一遍，并保证屏幕与之一致。

        两条重建臂各自只在「建新层且点亮」时补帧（这是它们一直的行为），所以这里
        统一补一次：否则会出现「报表 lit=false 而屏幕还挂着刚才那张脸」——那正是
        PORTRAIT-006 的逐字节判据要抓的形状。`write_frame=False` 是把补帧的责任收到
        这一个出口，不是关掉它。
        """
        pc = self._precompute
        self._rebuild_deform_for_landmarks(pc, write_frame=False)
        self._rehang_enhance(pc, replayed_for=replayed_for, write_frame=False)
        self._refresh_frame_after_drop(replayed_for)

    def _face_manual_done(self, action: str, *, note: str | None = None,
                          extra: dict | None = None) -> None:
        st = self._face_state()
        emit({"event": "face_manual", "action": action,
              "manual": st["manual"], "faces": st["faces"], "enabled": st["enabled"],
              "blocked": st["blocked"], "index": st["index"], "explicit": st["explicit"],
              "face": st, **st,
              **({"note": note} if note else {}), **(extra or {})})

    def _face_manual_action(self, action: str, p: dict) -> None:
        """人脸名单的人工动作（PORTRAIT-006）：关掉误检 / 恢复 / 补上漏检 / 撤掉补的那一张。

        为什么这四条也是引擎命令：这份账要进文档状态、进撤销栈、进工程文件，并且决定
        deform/enhance 能不能放行——全在引擎侧。前端只画按钮与发 index/框。
        """
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        pc = self._precompute
        if pc is None:
            emit({"event": "error", "error":
                  f"face {action} 需要先 precompute：人工账要叠在一份名单上，没有名单就没有"
                  "「关掉哪一只」与「补在哪个位置」可记——不许前端自己记一份空账（它会与"
                  "下一次分析结果对不上）"})
            return
        if action == "add":
            self._face_manual_add(p)
            return
        if action == "remove":
            self._face_manual_remove(p)
            return
        faces = pc.faces()
        raw, box = p.get("index"), p.get("box")
        idx = None
        if raw is not None:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                emit({"event": "error", "error": f"face index 要是整数，得到 {raw!r}"})
                return
            idx = int(raw)
            if idx != raw or not 0 <= idx < len(faces):
                emit({"event": "error", "error":
                      f"face index {raw} 不在名单里（这一轮探到 {len(faces)} 张脸）"})
                return
            box = faces[idx]["box"]
        elif box is not None:
            idx = self._match_face_by_iou(pc, box)
        else:
            emit({"event": "error", "error": "face disable/enable 要给 index 或 box"})
            return
        key = self._manual_box(box)
        if key is None:
            emit({"event": "error", "error": f"这一只没有可用的脸盒（得到 {box!r}）：人工账按盒认人"})
            return
        ledger = self._face_manual
        if action == "disable":
            if any(self._manual_box(b) == key for b in ledger["disabled"]):
                emit({"event": "error", "error": "这一只已经在人工禁用名单里"})
                return
            ledger["disabled"].append(key)
            if idx is not None and idx == int(self._face_index) and self._face_explicit:
                # 当前编辑对象就是这一只：选型先放下，生效值交给 _settle_face_layers 清
                self._face_index, self._face_box, self._face_explicit = 0, None, False
            disabled = self._disabled_indices(pc)
            enabled = [int(f["index"]) for f in faces if int(f["index"]) not in disabled]
            if len(enabled) == 1:
                # 只剩一个可编辑的人：那一步排除是人做的，直接指过去（与
                # `_preserve_face_choice` 末尾同一口径，两处不做两套判断）
                view = pc.select_face(enabled[0])
                self._precompute = view
                self._face_index = enabled[0]
                self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
                self._face_explicit = True
                note = (f"已关掉第 {idx} 只（误检）；名单里只剩 index {enabled[0]} 一个可编辑的人，"
                        "已指为当前编辑对象")
            else:
                note = f"已关掉第 {idx} 只（误检）：这一只不再被任何单脸作用域操作服务"
            self._settle_face_layers("face_disable")
            self._face_manual_done("disable", note=note)
            return
        # enable：把账上那一条撤掉。认不回的条目也能撤（给 index 走 IoU，给 box 走那条账本身），
        # 因为 stale 的禁用记录是用户唯一还需要清得掉的东西
        hit = None
        for i, b in enumerate(ledger["disabled"]):
            if b == key or (idx is not None and self._match_face_by_iou(pc, b) == idx):
                hit = i
                break
        if hit is None:
            emit({"event": "error", "error":
                  f"这一只不在人工禁用名单里（账上 {len(ledger['disabled'])} 条，"
                  "没有一条与它对上）：不静默报成功"})
            return
        ledger["disabled"].pop(hit)
        self._settle_face_layers("face_enable")
        self._face_manual_done("enable",
                               note=f"已恢复第 {idx if idx is not None else '?'} 只：它重新可以选定与服务")
        return

    def _face_manual_add(self, p: dict) -> None:
        """把用户框住的一张漏检的脸加进名单：点位来自**该区域的真检测**。

        这一条的存在理由是 DoD §2：不许伪装 AI，也不许做假控件。所以「手加一张脸」不是
        在框里画一个可拖的网格，而是**在这一框上再跑一次同一个后端**拿回 478 点；拿不到
        就明确拒绝并说清为什么（见 face.detect_region 的三条拒绝路径）。
        """
        from . import face as face_mod

        rect = p.get("rect") if p.get("rect") is not None else p.get("box")
        key = self._manual_box(rect)
        if key is None:
            emit({"event": "error", "error":
                  f"face add 要给归一化矩形 rect=(x0,y0,x1,y1)，得到 {rect!r}"})
            return
        if self._match_face_by_iou(self._precompute, key) is not None:
            emit({"event": "error", "error":
                  "这一框里已经有脸了（名单里有与它对得上的人）：要改他就用 `face select`，"
                  "重复入列会让同一张脸在名单里出现两次"})
            return
        if any(self._manual_box(b) == key for b in self._face_manual["added"]):
            emit({"event": "error", "error": "这一框已经在人工名单里"})
            return
        if getattr(self, "_src_rgb", None) is None:
            emit({"event": "error", "error": "没有可重跑区域检测的代理帧：请重新 load_image"})
            return
        # 用**当前这份名单出自的那个后端**再跑一次：换后端补框会让同一张图里两套点位并存，
        # 而面板上一律显示同一个 landmark_backend（那是看不出错的那一类错）
        backend = self._precompute_backend or "auto"
        try:
            fn = face_mod.build(backend)
        except (face_mod.MissingBackend, ValueError) as e:
            emit({"event": "error", "error": f"区域检测后端不可用({backend}): {e}"})
            return
        try:
            lm, info = face_mod.detect_region(fn, CDH.analysis_rgb(self), key)
            pc2 = self._precompute.with_manual_face(lm)
        except Exception as e:                        # noqa: BLE001
            emit({"event": "error", "error":
                  f"这一框里没有可服务的人脸，已拒绝，名单原样未动：{type(e).__name__}: {e}"})
            return
        new_idx = len(pc2.faces()) - 1
        view = pc2.select_face(new_idx)
        try:
            self._vram.load_face(view)
        except Exception as e:
            emit({"event": "error", "error": f"新名单上显存失败({type(e).__name__}): {e}，"
                                             "人工脸未入列，原名单继续服务"})
            return
        self._precompute = view
        self._face_manual["added"].append(key)
        # 用户框住它就是要改它：这一步指过去不是「引擎替他选」，而是那次框选本身就是选择
        self._face_index = new_idx
        self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
        self._face_explicit = True
        self._settle_face_layers("face_add")
        self._face_manual_done("add",
                               note=f"已按用户框补进一张人工脸（index {new_idx}，"
                                   f"点位出自 {info['backend']} 区域检测，IoU {info['iou']}）",
                              extra={"region": info})

    def _face_manual_remove(self, p: dict) -> None:
        """撤掉一张**人工补的**脸（补错了要能收回）。检测到的那一张不许撤，只能禁用。"""
        from dataclasses import replace

        from .face import _norm_box

        pc = self._precompute
        faces = pc.faces()
        raw = p.get("index")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            emit({"event": "error", "error": f"face remove 要给整数 index，得到 {raw!r}"})
            return
        idx = int(raw)
        if idx != raw or not 0 <= idx < len(faces):
            emit({"event": "error", "error": f"face index {raw} 不在名单里（{len(faces)} 张）"})
            return
        if not faces[idx]["manual"]:
            emit({"event": "error", "error":
                  f"第 {idx} 张是这一轮检测出来的脸，不能撤：要让它不服务请用 `face disable`"
                  "（人工账）。撤掉检测结果是另一件事——那是改模型的输出，不是改判断"})
            return
        pool = list(pc.all_landmarks or [pc.landmarks])
        del pool[idx]
        if not pool:
            emit({"event": "error", "error": "名单不能空：最后一张脸请用 `face disable` 处理"})
            return
        # 索引整体前移一格：删掉第 i 张之后「第 j 张」在 i 之后全部指向别人，不重编就是
        # 从这一刻起 index 与 chip 分家（本仓为这件事付过学费，见 _face_box 那条注释）
        manual = tuple(sorted({(i if i < idx else i - 1) for i in pc.manual if i != idx}))
        # 账上那条人工框要一起撤掉。认的是「这条框当初指到第 idx 张」，而不是拿两个盒子
        # 比逐位相等：框是用户画的，盒是点位算出来的，本来就不该相等——上一版按相等比，
        # 条目留在账上并标成 lost，下一轮重检测又把它补回名单：撤掉的脸自己活了回来
        tied = [b for b in self._face_manual["added"] if self._match_face_by_iou(pc, b) == idx]
        base = replace(pc, all_landmarks=pool, num_faces=len(pool), manual=manual)
        # `base.landmarks` 不能停在被删那一张上：下游（deform 建层、导出、vram）只读
        # `.landmarks`，留着就是一层无源之水。先指到第 0 张，下面再按盒认回用户选过那一张
        base = replace(base, landmarks=pool[0], face_index=0, face_box=_norm_box(pool[0]))
        # 当前选定那一张换了位置或没了：按盒认回来，认不回就放下选型（不拿旧序号指新人）
        keep = self._face_box
        self._precompute = base
        # 其余框留着：它们指的是别人，下一轮分析由 `_reapply_face_manual` 重新认
        self._face_manual["added"] = [b for b in self._face_manual["added"] if b not in tied]
        hit = self._match_face_by_box(base, keep) if keep is not None else None
        if hit is None and self._face_explicit:
            self._face_index, self._face_box, self._face_explicit = 0, None, False
        elif hit is not None:
            view = base.select_face(hit)
            self._precompute = view
            self._face_index = hit
            self._face_box = tuple(float(v) for v in (view.face_box or ())) or None
        self._settle_face_layers("face_remove")
        self._face_manual_done("remove", note=f"已撤掉人工补的第 {idx} 张：名单重新按索引连续编号")
        return

    # ------------------------------------------------------------ 层级合成（LNX-PORTRAIT-004）
    DEFORM_ACTIONS = ("set", "clear", "inherit")
    DEFORM_SCOPES = ("all", "person")
    DEFORM_KEYS = {"cmd", "action", "amounts", "scope"}

    @staticmethod
    def _person_key(box):
        """把脸盒折成可比较的键——这就是“那一张脸”的身份（与 _face_box 同一条理由）。"""
        if not box or len(box) != 4:
            return None
        return tuple(round(float(v), 5) for v in box)

    def _override_for(self, box) -> dict:
        """那一张脸上挂着的覆盖（没有就给空字典）。认的是脸盒，容差 1e-3。"""
        key = self._person_key(box)
        if key is None:
            return {}
        for o in self._deform_overrides:
            ob = self._person_key(o.get("box"))
            if ob and max(abs(a - b) for a, b in zip(ob, key)) < 1e-3:
                return dict(o.get("amounts") or {})
        return {}

    def _effective_deform_amounts(self) -> dict:
        """当前在改那一张脸的最终生效值（每格一个，键集 = KINDS）：默认打底，覆盖项逐 kind 盖上去。

        合成只在这一处。会话里那份 `_deform["amounts"]`、doc_state、出片、UI 滑块读的都是
        它的结果——写两处就会出现“面板显示默认而渲染用覆盖”那种双向错配。

        没有“那一张”（没分析过，或多人图还没选定）时生效值全零：`target_scope=single_face`
        的操作说不出对象就没有可合成的脸，而两份层级原样留着当用户意图，选定之后由
        `_rebuild_deform_for_landmarks` 接回来。拿“全人物默认”去服务一张说不出是谁的脸，
        正是 SCOPE-001 拦的那件事。
        """
        if self._people_managed():return dict(self._deform["amounts"])
        box = self._person_key(self._face_box)
        if box is None:
            return {k: 0.0 for k in KINDS}
        eff = {k: float(self._deform_default.get(k, 0.0) or 0.0) for k in KINDS}
        for k, v in self._override_for(box).items():
            if k in KINDS:
                eff[k] = float(v)
        return eff

    def _set_override(self, box, amounts: dict) -> None:
        """把这几个 kind 挂到那一张脸上（按 kind 增量，不把同一个人别的 kind 抹掉）。"""
        key = self._person_key(box)
        for o in self._deform_overrides:
            if self._person_key(o.get("box")) == key:
                o["amounts"].update({k: float(v) for k, v in amounts.items() if k in KINDS})
                return
        self._deform_overrides.append({"box": key,
                                       "amounts": {k: float(v) for k, v in amounts.items()
                                                   if k in KINDS}})

    def _drop_override(self, box) -> bool:
        """恢复继承：丢掉**那一张脸**的覆盖。返回真有没有得丢（空操作要说出口）。"""
        key = self._person_key(box)
        before = len(self._deform_overrides)
        self._deform_overrides = [o for o in self._deform_overrides
                                  if self._person_key(o.get("box")) != key]
        return len(self._deform_overrides) != before

    def _layered_deform_state(self) -> dict:
        """层级那一份账：`doc_state.deform` 与 `deform_done` 共用这一个组装点。

        前端不自己数“这一张被单独改过几格”：那份数只能从引擎的合成现场来，否则
        “面板说全继承而渲染带着覆盖”没人拦得住。
        """
        ov = self._override_for(self._face_box)
        return {"default": dict(self._deform_default),
                "overrides": [{"box": [float(v) for v in (o["box"] or ())],
                               "amounts": dict(o["amounts"])}
                              for o in self._deform_overrides],
                "overridden_kinds": sorted(ov),
                "inherited": not bool(ov)}

    def _deform_intent(self, st: dict | None = None) -> bool:
        """这份状态里有没有“用户的形变意图”（三层任一层非零就算有）。

        判据不写两遍：`_recipe_needs_landmarks`（重开要不要补分析）与关键点重建走的是
        同一句话，而漏掉“只有默认”或“只有别人的覆盖”那两种形状，代价分别是“重开少了
        一层”和“切回来静没掉”。
        """
        st = st if st is not None else self._capture_state()
        df = st.get("_deform") or {}
        if bool(df.get("built")) or bool(st.get("_deform_defer")):
            return True
        for src in (df.get("amounts") or {}, st.get("_deform_default") or {}):
            if any(abs(float(v)) > 0.0 for v in src.values()):
                return True
        return any((o.get("amounts") or {}) for o in (st.get("_deform_overrides") or []))

    def cmd_deform(self, p: dict):
        """五官微调：瘦脸 / 大眼 / 小下巴 / 微笑嘴角四个滑块（KINDS 是唯一出处，
        名单与值域随 ready 的 deform_kinds / deform_range 报出去），外加作用层（PORTRAIT-004）。

        与修容笔的区别：它不是逐笔图层而是一个“参数层”——滑块值就是全部状态；
        撤销/重做属于产品闭环（M5）统一做，不在这里先做三份中的一份。

        作用层（LNX-PORTRAIT-004）：`scope=all`（默认）改的是**全人物默认**那一层，
        `scope=person` 只给当前选定的那一张挂**覆盖**，`action=inherit` 把这一张的覆盖
        拿下来回到跟随默认。三条臂写的都是“某一层”，而送进会话的永远是合成结果
        （`_effective_deform_amounts()` 是唯一合成点）——所以“改一个 kind 把另一个 kind
        的单独覆盖抹掉”和“面板显示默认而渲染用的是覆盖”这两种错配都进不来。

        诚实边界：一层形变服务一张脸。单位场只从**那一张**脸的轮廓解控制点，所以同一
        时刻只有被选中那一张按它的有效值生效；换人就是换那份几何（不是“多人同时各改各
        的”，那种说法是假能力）。

        铁律与 light 同构：先全量校验、后一次性提交，被拒整条不留痕（层级两份一起退回）。
        建层需要 478 点关键点，而 **synthetic 后端给的是网格占位几何**：拿它按脸形语义
        取点会搬到完全无关的位置上，而且画面“真的动了”——看不出错。所以整条拒绝并说清原因。
        """
        if self._people_managed():return self._people_legacy("lnx.deform.v1",p,emit)
        unknown = set(p) - self.DEFORM_KEYS
        if unknown:
            emit({"event": "error", "error": f"deform 收到不认识的参数：{sorted(unknown)}"
                  f"（可用：{sorted(self.DEFORM_KEYS - {'cmd', 'action'})} / action）"})
            return
        action = p.get("action", "set")
        if action not in self.DEFORM_ACTIONS:
            emit({"event": "error", "error": f"未知 deform action: {action}"
                  f"（可用：{'/'.join(self.DEFORM_ACTIONS)}，名单在 ready 的 deform_actions 里）"})
            return
        scope = p.get("scope", "all")
        if scope not in self.DEFORM_SCOPES:
            emit({"event": "error", "error": f"未知 deform scope: {scope}"
                  "（可用：all=改全人物默认 / person=只覆盖当前选定那一张，"
                  "名单在 ready 的 deform_scopes 里）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
                  f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
                  "请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 deform：先 bench_stop"})
            return
        # 超范围保护（SCOPE-001 / D-P0-02）：面部重塑是 target_scope=single_face 的操作。
        # 多人同图时不拿“其中某一张”冒充“那张脸”——静默选型正是冻结件点名要防的那件事，
        # 而且用户从画面上看不出来（脸确实被推了，推的不是他以为的那一个）。
        # `scope=person` 与 `inherit` 也在说“这一张”，所以一起挡：说不出是谁就不许假装办过。
        # 只拒这一条：全图调色/曝光/裁剪/磨皮的作用面不是“某个人”，不受影响。
        pc0 = self._precompute
        addresses_a_person = scope == "person" or action == "inherit"
        if (action == "set" or addresses_a_person) and pc0 is not None:
            blocked, why = self._face_guard()
            if blocked:
                emit({"event": "error", "error": why})
                return
        # 身份：这一层挂在**脸盒**上（PORTRAIT-004）。没有脸盒就没有可挂的对象，也没有
        # 可合成的那一张。`clear` + `scope=all` 是唯一的例外：那是“整层放下”，
        # 不需要知道是谁，也不该因为没分析过而按不动（清空按钮必须永远能按）。
        if not (action == "clear" and scope == "all") and not self._person_key(self._face_box):
            emit({"event": "error", "error":
                  f"deform 需要先 precompute（多人图还要先 `face select` 选定那一张）："
                  "形变层挂在脸盒身份上（PORTRAIT-004），没有脸盒就不知道该把这一层挂到"
                  "谁身上、也不知道该按谁的覆盖合成"})
            return
        t_start = monotonic_ns()
        build_info: dict = {}
        prev_amounts = dict(self._deform["amounts"])
        prev_built = bool(self._deform["built"])
        # 两份层级各自快照：被拒或渲染抛了都要原样退回。只退回合成结果就会留下
        # “画面回到上一帧而层级记着新的那一份”，而下一次切文档/存工程会把那半成品存出去
        prev_default = dict(self._deform_default)
        prev_overrides = [{"box": o["box"], "amounts": dict(o["amounts"])}
                          for o in self._deform_overrides]

        def _rollback_layers() -> None:
            self._deform_default = prev_default
            self._deform_overrides = prev_overrides

        note: str | None = None
        if action == "clear" and scope == "all":
            # 整层清空：默认与每一个人的覆盖一起走。只清默认、留着覆盖就是“清空了而画面
            # 还带着单独改过的那几张”，用户会以为清空按钮没生效
            self._vram.clear_deform()
            self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
            # 用户亲口说“不要这一层”：存住的那一份意图一起清，不然下一次分析又把它复活
            self._deform_defer = False
            self._deform_default = {k: 0.0 for k in KINDS}
            self._deform_overrides = []
        else:
            if action == "set":
                try:
                    # 参数先于建层也先于落层：越界值不该付一次 55 ms 解算，也不该写进层级
                    got = check_amounts(p.get("amounts"))
                except ValueError as e:
                    emit({"event": "error", "error": f"deform 被拒，整条拒绝：{e}"})
                    return
                # 写进它该去的那一层，而不是写进合成结果：改默认不该把别的 kind 变成覆盖
                if scope == "all":
                    self._deform_default.update(got)
                else:
                    self._set_override(self._face_box, got)
            else:
                # `clear`(person) 与 `inherit` 同义：把这一张的覆盖拿下来，默认一个字不动。
                # 认不回那一张（本来就没单独改过）返回 False——那不是错误，是空操作，
                # 但必须说出口：否则“按了恢复继承而画面没变”就又是一件查不清的事
                if not self._drop_override(self._face_box):
                    # 格数由 KINDS 报，不许写死：写死的那一句会印在面板上，
                    # 而面板新增一格时它就成了一句当场的假话。
                    note = (f"这一张本来就没有覆盖（全部 {len(KINDS)} 格都跟随全人物默认），"
                            "本次 inherit/clear(person) 是空操作")
            eff = self._effective_deform_amounts()
            EYER.check_legacy(self._eye_shape,eff)
            if not any(abs(float(v)) > 0.0 for v in eff.values()):
                # 合成出来全零 = 这一张身上没劲儿：会话里那一层要放下。留着就是一个
                # “看不见的层”继续占常驻字节，而 `lit=false` 与 `bytes_deform>0` 互相打脸
                if self._deform["built"]:
                    self._vram.clear_deform()
                self._deform = dict(amounts=eff, built=False)
                self._deform_defer = False
            else:
                if not self._deform["built"]:
                    pc = self._precompute
                    if pc is None:
                        _rollback_layers()
                        emit({"event": "error", "error":
                              "形变需要先 precompute：没有 478 点关键点就不知道把哪里搬到哪里"
                              + ("（上一层的参数已经存住等重挂，跑一次 precompute 就接回去）"
                                 if self._deform_defer else "")
                              + "；全人物默认与逐张覆盖两份已原样退回"})
                        return
                    if pc.backend == "synthetic":
                        _rollback_layers()
                        emit({"event": "error", "error":
                              "形变拒绝 synthetic 后端的关键点：它们是网格占位几何、不是脸形，"
                              "按点号取“左脸轮廓”会搬到无关位置。请装 mediapipe 插件后端"
                              "；层级两份已原样退回"})
                        return
                    try:
                        built = self._vram.build_deform(pc.landmarks)
                    except (DeformGeometryError, ValueError, RuntimeError) as e:
                        _rollback_layers()
                        emit({"event": "error", "error": f"形变建层失败，整条拒绝：{e}"
                              "；全人物默认与逐张覆盖两份已原样退回"})
                        return
                    self._deform["built"] = True
                    self._deform_defer = False
                    build_info = {"build": built}
                try:
                    # 送进会话的是**合成结果**（默认打底 + 这一张的覆盖），不是刚传来的
                    # 那几个数：只传增量就会让“改一个 kind 把另一个 kind 的覆盖丢掉”
                    info = self._vram.set_deform_amounts(eff)
                except ValueError as e:
                    _rollback_layers()
                    emit({"event": "error", "error": f"deform 被拒，整条拒绝：{e}"
                          "；层级两份已原样退回"})
                    return
                self._deform["amounts"] = dict(info["amounts"])
        try:
            fr = self._write_current_frame("deform")
        except Exception as e:
            # 值已写进常驻层而渲染抛了（apply_deform 的非有限值护栏、会话尺寸不配）：
            # 必须退回上一条已证能出帧的状态——层级两份、合成结果与 built 一起退。
            # 只退 amounts 就会留下“层级记着新的而画面停在旧的”，下一次切文档把半成品存出去。
            _rollback_layers()
            self._deform = dict(amounts=prev_amounts, built=prev_built)
            self._deform_defer = (not prev_built) and any(
                abs(float(v)) > 0.0 for v in prev_amounts.values())
            try:
                if prev_built and self._precompute is not None \
                        and self._precompute.backend != "synthetic":
                    # clear(all) 那一条臂已经把单位场放下了：回滚要把场一起建回来，
                    # 不然 `set_deform_amounts(prev)` 写进的是一个没有单位场的会话，
                    # 报出来的 amounts 非零而 lit=false——又是一处看不出的错配
                    self._vram.build_deform(self._precompute.landmarks)
                self._vram.set_deform_amounts(prev_amounts)
                back = self._write_current_frame("deform")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚也出帧失败：能说清的只有“重新导图”
                emit({"event": "engine_warn",
                      "warn": "形变回滚后仍无法出帧，本会话不可信，请重新导入图片"})
            emit({"event": "error", "error": f"形变渲染失败，滑块与层级已退回上一值（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms")
        self._emit_deform_state(action, build=build_info.get("build"),
                                render_ms=render_ms,
                                total_ms=round((monotonic_ns() - t_start) / 1e6, 2),
                                scope=scope, reason=note)
        emit(fr)

    # ------------------------------------------------------------ 调色（M3-a2）与预设（M3-b）
    def _primary_calibration_service(self):
        from .primary_calibration_service import Service
        if '_primary_calibration_service_owner' not in self.__dict__:self._primary_calibration_service_owner=Service()
        return self._primary_calibration_service_owner

    def cmd_primary_calibration(self,p):return self._primary_calibration_service().execute(self,p,emit)
    def cmd_primary_calibration_state(self,p):
        emit({'event':'primary_calibration_readback','request_id':p.get('request_id'),'result':self._primary_calibration_service().readback(self),'success':True})

    def _colour_editor_service(self):
        from .colour_editor_service import Service
        if '_colour_editor_service_owner' not in self.__dict__: self._colour_editor_service_owner=Service()
        return self._colour_editor_service_owner
    def _colour_editor_capture(self):
        from .colour_editor_sampling import ColourEditorCapture
        if '_colour_editor_capture_owner' not in self.__dict__: self._colour_editor_capture_owner=ColourEditorCapture(self,emit)
        return self._colour_editor_capture_owner
    def cmd_colour_editor(self,p): return self._colour_editor_service().execute(self,p,emit)
    def cmd_colour_editor_state(self,p):
        emit({'event':'colour_editor_readback','request_id':p.get('request_id'),'result':self._colour_editor_service().readback(self),'success':True})
    def cmd_colour_editor_sample(self,p):
        try: emit(self._colour_editor_capture().probe(p))
        except Exception as error: emit({'event':'colour_editor_sample','request_id':p.get('request_id'),'success':False,'status':'failed','error':str(error)[:1000]})

    def _selective_colour_service(self):
        from .selective_colour_service import Service
        if '_selective_colour_service_owner' not in self.__dict__:self._selective_colour_service_owner=Service()
        return self._selective_colour_service_owner

    def cmd_selective_colour(self,p):return self._selective_colour_service().execute(self,p,emit)
    def cmd_selective_colour_state(self,p):
        emit({'event':'selective_colour_readback','request_id':p.get('request_id'),'result':self._selective_colour_service().readback(self),'success':True})

    def _photo_grain_service(self):
        from .photo_grain_service import Service
        if '_photo_grain_service_owner' not in self.__dict__:self._photo_grain_service_owner=Service()
        return self._photo_grain_service_owner

    def cmd_photo_grain(self,p):return self._photo_grain_service().execute(self,p,emit)
    def cmd_photo_grain_state(self,p):
        emit({'event':'photo_grain_readback','request_id':p.get('request_id'),'result':self._photo_grain_service().readback(self),'success':True})

    def _colour_grading_service(self):
        from .colour_grading_service import Service
        if '_colour_grading_service_owner' not in self.__dict__:self._colour_grading_service_owner=Service()
        return self._colour_grading_service_owner

    def cmd_colour_grading(self,p):return self._colour_grading_service().execute(self,p,emit)
    def cmd_colour_grading_state(self,p):
        emit({'event':'colour_grading_readback','request_id':p.get('request_id'),'result':self._colour_grading_service().readback(self),'success':True})

    def _photo_detail_service(self):
        from .photo_detail_service import Service
        if '_photo_detail_service_owner' not in self.__dict__:self._photo_detail_service_owner=Service()
        return self._photo_detail_service_owner

    def cmd_photo_detail(self,p):return self._photo_detail_service().execute(self,p,emit)
    def cmd_photo_detail_state(self,p):
        emit({'event':'photo_detail_readback','request_id':p.get('request_id'),'result':PDH.readback(self),'success':True})
    def cmd_photo_detail_receipt(self,p):
        owner=PDH.controller(self,emit,preview_scale=lambda:PDH.preview_scale(self))
        emit(owner.query(p.get('request_id')))

    def _extended_tone_service(self):
        from .extended_tone_service import Service
        if '_extended_tone_service_owner' not in self.__dict__:self._extended_tone_service_owner=Service()
        return self._extended_tone_service_owner

    def cmd_extended_tone(self,p):return self._extended_tone_service().execute(self,p,emit)
    def cmd_extended_tone_state(self,p):
        emit({'event':'extended_tone_readback','request_id':p.get('request_id'),'result':ETH.readback(self),'success':True})
    def cmd_extended_tone_receipt(self,p):
        owner=ETH.controller(self,emit,preview_scale=lambda:ETH.preview_scale(self),monochrome=lambda:ETS.check(self._extended_tone)['monochrome'])
        emit(owner.query(p.get('request_id')))

    def _custom_lut_service(self):
        from .custom_lut_service import Service
        if "_custom_lut_owner" not in self.__dict__: self._custom_lut_owner = Service()
        return self._custom_lut_owner

    def cmd_custom_lut(self, p):
        return self._custom_lut_service().execute(self, p, emit)

    def _custom_lut_reader_stop(self):
        self._photo_detail_service().stop()
        self._extended_tone_service().stop()
        self._photo_grain_service().stop()
        self._colour_grading_service().stop()
        self._primary_calibration_service().stop()
        self._selective_colour_service().stop()
        self._colour_editor_service().stop()
        owner = self.__dict__.get("_custom_lut_owner")
        if owner is not None:
            with owner.lock:
                for key, event in owner.events.items():
                    if not (owner.active == key and owner.published): event.set()
        self._owned_reader_stop()

    def _custom_lut_ingress(self, line):
        primary_consumed=self._primary_calibration_service().ingress(line)
        selective_consumed=self._selective_colour_service().ingress(line)
        editor_consumed=self._colour_editor_service().ingress(line)
        grain_consumed=self._photo_grain_service().ingress(line)
        grading_consumed=self._colour_grading_service().ingress(line)
        detail_consumed=self._photo_detail_service().ingress(line)
        tone_consumed=self._extended_tone_service().ingress(line)
        lut_consumed=self._custom_lut_service().ingress(line)
        owned_consumed=self._owned_command_ingress(line)
        return editor_consumed or detail_consumed or primary_consumed or selective_consumed or grain_consumed or grading_consumed or tone_consumed or lut_consumed or owned_consumed

    def _resolve_lut_source(self, p: dict):
        """从命令里解析出那张表：path / text / preset 三个来源必给且只给一个。

        返回 `(cube, preset_or_None)`：走 preset 那一臂时还要把预设的肤色定向一并提交
        （一个预设 = 一张表 + 三个数），返回的第二个元素就是那个预设对象。
        失败自己发 error 返 None。

        为什么不“都给就用 text”：两个来源并存时先选一个就是替用户做决定，而两个表
        往往正好不一样——拿到哪个都是“对的那张的错版本”。当场拒比猜安全。
        """
        if "_custom_cube" in p:
            from .custom_lut_asset import CustomCube
            if not isinstance(p["_custom_cube"], CustomCube): raise ValueError("非法自定义 LUT")
            return p["_custom_cube"], None
        given = [k for k in ("path", "text", "preset") if p.get(k)]
        if len(given) != 1:
            emit({"event": "error",
                  "error": f"lut set 需要且只能给一个来源（path / text / preset），收到 "
                           f"{len(given)} 个{('：' + ', '.join(given)) if given else ''}"})
            return None
        key = given[0]
        try:
            if key == "path":
                return load_cube_file(str(p["path"])), None
            if key == "text":
                return parse_cube(str(p["text"]), source="text"), None
            preset = get_preset(p["preset"])
            return preset_lut(preset.name), preset
        except (LutError, PresetError, OSError, UnicodeDecodeError, ValueError) as e:
            # 整条拒：不留“解了一半”的表。上一轮“预计算失败留半截显存”同一形状。
            # 事件里的词沿用 “LUT 被拒”（test_protocol 一直在卡这个字面，也是报表里最好认的一个）。
            emit({"event": "error", "error": f"LUT 被拒，整条不生效（{type(e).__name__}）：{e}"})
            return None

    def _restore_lut(self, prev) -> None:
        """回到上一条已证能出帧的调色状态（补帧失败与回滚两条臂共用）。"""
        cube, amount = prev
        try:
            if cube is None:
                self._vram.clear_lut()
            else:
                self._vram.set_lut(cube, amount)
        except Exception as e:      # 回滚再失败就只能说清“重新导图”，不留一个看起来已回滚的状态
            emit({"event": "engine_warn",
                  "warn": f"调色层回滚失败（{type(e).__name__}）：{e}，本会话不可信，请重新导入图片"})

    def _restore_grade(self, prev, prev_scope=None, prev_mask=None) -> None:
        """回滚肤色定向层（带作用域与画笔区域）。与 _restore_lut 同一条：回滚再失败就明说“重新导图”。

        顺序必须是 mask → scope：brush 没有区域会被库层当场拒（那条拒不是洁癖，是
        “拿不到掩膜就不能只调那一片”）。prev_scope 缺省（cmd_lut 那条旧调用只回滚四个数）
        时不动作用域——它本来也不碰这一层。
        """
        try:
            if prev == (0.0, 0.0, 0.0, 1.0):
                self._vram.clear_grade()
            else:
                self._vram.set_grade(prev[0], prev[1], prev[2], amount=prev[3])
            if prev_scope is not None:
                if prev_mask is None:
                    self._vram.clear_grade_mask()
                else:
                    self._vram.set_grade_mask(prev_mask, mode="replace")
                self._vram.set_grade_scope(str(prev_scope))
        except Exception as e:
            emit({"event": "engine_warn",
                  "warn": f"肤色定向回滚失败（{type(e).__name__}）：{e}，本会话不可信，"
                          "请重新导入图片"})

    def _emit_lut_state(self, action: str, info: dict, *, render_ms: float = 0.0,
                        total_ms: float = 0.0,
                        preset_grade_cleared: bool = False) -> None:
        """lut_done 的唯一组装点（set/clear/amount 三条臂共用一份形状）。

        图层字段全部来自 vram._lut_payload，这里只加计时与每帧那几笔。与
        _precompute_ready_event / _emit_deform_state 同一条理由：两处各写一份必然漂，
        而 TS 把字段声明成必存——谎报发生在 JSON 边界上，编译期抓不到。
        """
        pipe = self._vram
        emit({"event": "lut_done", "action": action, **info,
              # 这一帧真跑了多少调色（挂上表且强度非 0 时 > 0；为 0 就是那层没跑）
              "lut_ms": round(float(pipe.last_lut_ms), 2),
              # M3-b：预设一条命令同时动两层，所以 lut_done 必须能说出定向那层的现状：
              # 否则 UI 只能自己记一份数，而引擎里那一层可能因为回滚已经变了。
              # 它与 grade_done 里的 grade_ms 同一出处（都取自局部 pipe），不是第2个口径。
              "grade_ms": round(float(pipe.last_grade_ms), 2),
              "grade_state": dict(dh=float(pipe.grade_params[0]), ds=float(pipe.grade_params[1]),
                                  dv=float(pipe.grade_params[2]), amount=float(pipe.grade_amount),
                                  lit=bool(pipe.has_grade()),
                                  bytes_grade=int(pipe.grade_resident_bytes())),
              # 当前生效的预设名（没走预设就是 None）：UI 靠它区分“预设强度”与
              # “自己载的表”，而不是自己记住上一次按了哪个按钮
              "lut_preset": self._lut_preset,
              # 这次 clear 有没有连带把预设那份肤色定向一起拿掉。它不是计时也不是
              # 分段，但三条臂都得带：少一个键在 TS 侧就是一个 undefined（M3-b 为
              # grade_state 的形状付过学费）。
              "preset_grade_cleared": bool(preset_grade_cleared),
              # 这两条是“设 LUT 不作废磨皮缓存”的直接证据：补的那一帧仍应命中
              "filter_ms": round(float(pipe.last_filter_ms), 2),
              "bands_ms": round(float(pipe.last_bands_ms), 2),
              "filter_cached": float(pipe.last_filter_ms) == 0.0,
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              "strength": self._strength})

    def cmd_lut(self, p: dict):
        """3D LUT 调色（M3-a2）：载入/清除一张表，或只改混合系数。

        与 light/deform 同一套铁律：跑靶互斥、先全量校验后一次性提交、被拒整条不留痕、
        事件只有一个组装点。与它们的区别在于本层不依赖关键点也不依赖笔迹：
        换设备要重挂（体积活在那块卡上），但不随磨皮/修容参数作废任何缓存。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear", "amount"):
            emit({"event": "error", "error": f"未知 lut action: {action}（可用：set/clear/amount）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
                  f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
                  "请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 lut：先 bench_stop"})
            return
        t_start = monotonic_ns()
        prev = (self._lut, self._lut_amount)
        prev_grade = self._grade
        prev_preset = self._lut_preset
        # 只有"带预设身份的 clear"会把它置真；lut_done 三条臂必须带同一个键，
        # 所以它在任何臂上都得先有个值。
        grade_with_preset = False
        if action == "set":
            # 强度先校：不能先付一次解析 + 上显存再发现参数非法（与 cmd_deform“参数先于建层”同形）
            amount = None
            if p.get("amount") is not None:
                try:
                    amount = check_amount(p["amount"])
                except LutError as e:
                    emit({"event": "error", "error": f"lut 被拒，整条不生效：{e}"})
                    return
            got = self._resolve_lut_source(p)
            if got is None:
                return
            cube, preset = got
            gvals = None
            if preset is not None:
                # 预设同时动两层，那两层的参数都得先过完才能开始提交：先挂表再拒
                # 参数就是“半应用”（M1-3c/M2-a2 审查里同一个形状）。
                # 强度一个数管两层：预设的“50%”应当是整预设 50%，不是表 50% + 定向 100%。
                try:
                    gvals = check_params(*preset_grade(preset.name),
                                         amount=(1.0 if amount is None else float(amount)))
                except GradeError as e:
                    emit({"event": "error", "error": f"预设 {preset.name} 被拒，两层均未改动：{e}"})
                    return
            try:
                info = self._vram.set_lut(cube, amount)
            except (LutError, RuntimeError, ValueError) as e:
                # 库层只在全部可失败步骤之后才赋值，所以这里会话状态原样未动；
                # 引擎侧那两个字段也必须不动，否则下一条 set 会以为已经挂上了这张表
                emit({"event": "error", "error": f"调色层被拒，会话原样未动（"
                      f"{type(e).__name__}）：{e}"})
                return
            self._lut, self._lut_amount = self._vram.lut, float(self._vram.lut_amount)
            # 预设身份记在引擎侧：它决定“调色强度”要不要连带施加到定向层（见 amount 臂）。
            # 走 path/text 就是用户自己拿表说话，预设身份当场清掉。
            self._lut_preset = preset.name if preset is not None else None
            if gvals is not None:
                # 参数已在上一步校过，这里的提交不会再拒：预设要么两层都上，要么都不上。
                # 不拿它的返回值当 info：那会把 lut_done 的形状换成 grade 的那份（就是
                # M2 审 ⑤ “字典后写吃先写”同一个形状，本轮协议用例一个 KeyError 抽出来的）。
                # 定向层的现状由 _emit_lut_state 直接从 pipe 组装，只有一个出处。
                self._vram.set_grade(gvals[0], gvals[1], gvals[2], amount=gvals[3])
                self._grade = gvals
        elif action == "amount":
            if p.get("amount") is None:
                emit({"event": "error", "error": "lut amount 什么也没给：需要一个 0–1 的数值"})
                return
            try:
                amount = check_amount(p["amount"])
            except LutError as e:
                emit({"event": "error", "error": f"lut 被拒，整条不生效：{e}"})
                return
            try:
                info = self._vram.set_lut_amount(amount)
            except (LutError, RuntimeError, ValueError) as e:
                emit({"event": "error", "error": f"调色强度被拒，会话原样未动：{e}"})
                return
            self._lut_amount = float(self._vram.lut_amount)
            if self._lut_preset is not None:
                # 这一句不是“强度顺便也给定向层用”那么顺手：它是预设语义的必要一半。
                # `lut set preset=creamy amount=0.5` 把两层同时拉到 50%，之后只拖
                # “预设强度”滑块走的就是这一臂——不同步定向层就会“表淡了、肤色还满调”。
                # 只对走过预设的会话生效（_lut_preset 非空）：用户自己载表 + 手动调肤色时，
                # 表的强度不该伸到另一层里去。
                try:
                    self._vram.set_grade_amount(amount)
                    self._grade = (self._vram.grade_params[0], self._vram.grade_params[1],
                                   self._vram.grade_params[2], float(self._vram.grade_amount))
                except GradeError as e:
                    emit({"event": "error", "error": f"预设强度连带定向层被拒，已整条回滚：{e}"})
                    self._lut, self._lut_amount = prev
                    self._restore_lut(prev)
                    return
        else:
            info = self._vram.clear_lut()
            self._lut, self._lut_amount = None, 1.0
            # 预设是两层（表 + 肤色定向），set 那一臂自己写着“预设要么两层都上，
            # 要么都不上”——clear 不跟着对称就是半个撤销：用户按了“清除调色”，
            # 表下来了，预设写进定向层的那份肤色还留在画面上，而面板上已经没有任何
            # 东西指着它。只在会话带着预设身份时一起下：用户自己载表 + 手动调
            # 肤色时（cmd_grade 已把 _lut_preset 清成 None），那份肤色是他的，
            # 清调色表不许伸进另一层去拿他的东西。
            if self._lut_preset is not None:
                self._vram.clear_grade()
                self._grade = (0.0, 0.0, 0.0, 1.0)
                grade_with_preset = True
            else:
                grade_with_preset = False
            self._lut_preset = None
        try:
            fr = self._write_current_frame("lut")
        except Exception as e:
            # 表/强度已写进常驻层而渲染抛了：必须退回上一条已证能出帧的状态。
            # cmd_deform 为同一个形状付过钱：“拒绝了但画面变了”比报错难查得多。
            self._custom_lut_publication = None
            self._vram.custom_lut_cancelled = lambda: False
            self._lut, self._lut_amount = prev
            self._grade = prev_grade
            self._lut_preset = prev_preset
            self._restore_lut(prev)
            self._restore_grade(prev_grade)
            # prev_preset 里带着“这次 clear 要不要连带定向层”的判断依据：渲染失败
            # 回滚时两层必须一起回到 prev 那一版（上面提交时是一起提交的）。
            # _restore_grade 按 prev_grade 那一份参数重放，与预设身份无关，所以这里
            # 不需要再判一次 preset。
            try:
                back = self._write_current_frame("lut")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
                emit({"event": "engine_warn", "warn": "调色回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"调色渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms")
        self._emit_lut_state(action, info, render_ms=render_ms,
                             total_ms=round((monotonic_ns() - t_start) / 1e6, 2),
                             preset_grade_cleared=grade_with_preset)
        emit(fr)
        return True

    def _emit_grade_state(self, action: str, info: dict, *, render_ms: float = 0.0,
                          total_ms: float = 0.0) -> None:
        """grade_done 的唯一组装点（set/clear/amount 三条臂共用一份形状）。

        与 _emit_lut_state 同构：图层字段全部来自 vram._grade_payload，这里只加计时
        与每帧那几笔。字段集在两层之间对齐不是强迫症：哪一臂的 payload 少一个键，
        TS 侧就是个运行时 TypeError，而编译期抓不到。
        """
        pipe = self._vram
        emit({"event": "grade_done", "action": action, **info,
              # 这一帧真跑了多少定向（点火时 > 0；为 0 就是那层没跑，或走的是结构短路）
              "grade_ms": round(float(pipe.last_grade_ms), 2),
              # 调色层现状：手动改肤色会清掉预设身份，而“表还在不在”只能由事件说
              "lut_ms": round(float(pipe.last_lut_ms), 2),
              "lut_preset": self._lut_preset,
              "filter_ms": round(float(pipe.last_filter_ms), 2),
              "bands_ms": round(float(pipe.last_bands_ms), 2),
              "filter_cached": float(pipe.last_filter_ms) == 0.0,
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              "strength": self._strength})

    def cmd_background(self, p: dict):
        from .id_background_legacy import legacy_background
        if IDS.active(self._id_background) and p.get('action','set')=='set':
            raise ValueError('请先关闭已审核证件照换背景')
        return legacy_background(self,p,emit)

    def _src_gpu_norm(self):
        """当前会话源图 → (1,3,H,W) [0,1] float 常驻张量（供 birefnet 前向）。"""
        import torch

        pipe = self._vram
        x = pipe.src_f32
        if x is None:
            raise RuntimeError("会话尚未加载源图")
        return x if x.dtype == torch.float32 else x.to(torch.float32)

    def cmd_crop(self, p: dict):
        """裁剪 / 旋转（P0 注册表的 lnx.crop.v1：rect_normalized + rotation_degrees）。

        铁律沿用 cmd_exposure：跑靶互斥、整组校验后一次提交、被拒不留痕、出帧失败
        回滚并补帧。量程不在这里写字面量——`geometry_state()` 把硬上限随事件报出去。

        正角定义为**顺时针**（Lightroom/Capture One 的右转习惯）；两臂与预览/导出
        都走 ops.geometry 里那一个式子，改符号要一起改，这里不另立一套。
        """
        from .ops.geometry import GeometryError

        action = p.get("action", "set")
        if action not in ("set", "clear"):
            emit({"event": "error", "error": f"未知 crop action: {action}（可用：set/clear）"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝改裁剪：先 bench_stop"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        prev_rect = tuple(self._crop_rect)
        prev_rot = float(self._crop_rotation)
        if action == "clear":
            st = self._vram.clear_geometry()
            self._crop_rect = (0.0, 0.0, 1.0, 1.0)
            self._crop_rotation = 0.0
        else:
            rect = p.get("rect", list(self._crop_rect))
            rot = p.get("rotation_degrees", self._crop_rotation)
            if p.get("rect") is None and p.get("rotation_degrees") is None:
                emit({"event": "error", "error": "crop set 什么也没给：至少给 rect 或 "
                      "rotation_degrees，或者走 clear 把整层关掉"})
                return
            try:
                st = self._vram.set_geometry(rect, rot)
            except (GeometryError, ValueError) as e:
                emit({"event": "error", "error": f"裁剪/旋转被拒，整条不生效：{e}"})
                return
            self._crop_rect = tuple(st["crop_rect"])
            self._crop_rotation = float(st["crop_rotation"])
        try:
            fr = self._write_current_frame("crop")
        except Exception as e:
            self._crop_rect = prev_rect
            self._crop_rotation = prev_rot
            try:
                if prev_rect == (0.0, 0.0, 1.0, 1.0) and prev_rot == 0.0:
                    self._vram.clear_geometry()
                else:
                    self._vram.set_geometry(prev_rect, prev_rot)
                back = self._write_current_frame("crop")
                back.pop("render_ms", None)
                emit(back)
            except Exception:
                emit({"event": "engine_warn", "warn": "裁剪回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"裁剪/旋转渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        # crop_out 是**代理档**上剪转后的尺寸（预览那一层就是它，只是又缩回画布）；
        # out_full 才是导出会写的真实像素数，取自底片条那一行记的满幅尺寸。
        # 两个数一起报出去，UI 才不会把"预览里那一小块"讲成"文件的尺寸"。
        fr.setdefault("crop", {}).update(self._vram.geometry_state())
        # 带一份整张文档的状态：宿主只轮询 doc_state（frame 事件以前不进那一格），
        # 不带的话拖完裁剪滑块，面板上的数字就停在上一笔——“按了而不动”最难查
        fr["doc_state"] = self.doc_state()
        row = None
        for d in self._docs:
            if d["path"] == os.path.abspath(str(self._doc_path or "")):
                row = d
                break
        if row and row.get("src_w") and row.get("src_h"):
            from .ops.geometry import out_size as _gs
            fr["crop"]["out_full"] = list(
                _gs(int(row["src_w"]), int(row["src_h"]), self._crop_rect, self._crop_rotation))
        emit(fr)

    def cmd_exposure(self, p: dict, *, preserve_reference=False):
        """全局曝光与白平衡（P0 注册表的 lnx.exposure / lnx.white_balance）。

        铁律逐字沿用 cmd_grade/cmd_lut：跑靶互斥、先全量校验后一次性提交、被拒整条
        不留痕、出帧失败回滚 + 补帧、事件只有一个组装点。这一层不持有张量也不参与
        任何缓存键：改它不会让滤波重算，反向也一样。

        量程不靠这里的字面量：引擎把硬上限随每次事件报出去（exposure_limits），
        UI 自己抄一份数是两个会漂的地方。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear"):
            emit({"event": "error", "error": f"未知 exposure action: {action}（可用：set/clear）"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝改曝光：先 bench_stop"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        prev = tuple(self._exposure)
        prev_ref = self._exposure_ref_k
        prev_options = WB.check_options(self._wb_options)
        if action == "clear":
            st = self._vram.clear_exposure()
            self._exposure = (0.0,) * 7
            self._exposure_ref_k = None
            self._wb_options = WB.default_options()
        else:
            given = {k: p[k] for k in ("ev", "temperature_shift", "tint_shift",
                                        "contrast", "highlights", "shadows",
                                        "saturation")
                     if p.get(k) is not None}
            if not given and p.get("reference_k") is None and "wb_options" not in p:
                emit({"event": "error", "error": "exposure set 什么也没给：至少给一个参数，"
                      "或者走 clear 把整层关掉"})
                return
            cur = list(self._exposure)
            names = {"ev": 0, "temperature_shift": 1, "tint_shift": 2,
                     "contrast": 3, "highlights": 4, "shadows": 5,
                     "saturation": 6}
            for k, v in given.items():
                cur[names[k]] = v
            try:
                options = WB.check_options(p["wb_options"]) if "wb_options" in p else prev_options
                # 部分提交：拖一个滑块不该把另两个抹零，但合出来的那组必须整组校过
                st = self._vram.set_exposure(cur[0], cur[1], cur[2],
                                             ref_k=p.get("reference_k", self._exposure_ref_k),
                                             contrast=cur[3], highlights=cur[4],
                                             shadows=cur[5], saturation=cur[6], wb_options=options)
            except (ValueError, RuntimeError, OSError) as e:
                emit({"event": "error", "error": f"曝光/白平衡被拒，整条不生效：{e}"})
                return
            self._exposure = (float(st["exposure_ev"]),
                              float(st["exposure_temperature_shift"]),
                              float(st["exposure_tint_shift"]),
                              float(st["tone_contrast"]),
                              float(st["tone_highlights"]),
                              float(st["tone_shadows"]),
                              float(st["tone_saturation"]))
            self._exposure_ref_k = prev_ref if preserve_reference else float(st["exposure_reference_k"])
            self._wb_options = options
        try:
            fr = self._write_current_frame("exposure")
        except Exception as e:
            self._exposure = prev
            self._exposure_ref_k = prev_ref
            self._wb_options = prev_options
            rollback_ok = True
            try:
                self._vram.set_exposure(*prev[:3], ref_k=6500.0 if prev_ref is None else prev_ref,
                                        contrast=prev[3], highlights=prev[4], shadows=prev[5],
                                        saturation=prev[6], wb_options=prev_options)
                back = self._write_current_frame("exposure")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
                self._vram = None
                rollback_ok = False
                emit({"event": "engine_warn", "warn": "曝光回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            outcome = "已退回上一状态" if rollback_ok else "配方已恢复，但画面回滚失败；请重新导入"
            emit({"event": "error", "error": f"曝光渲染失败，{outcome}（{type(e).__name__}）：{e}"})
            return
        fr.setdefault("exposure", {})
        fr["exposure"].update(self._vram.exposure_state())
        fr["doc_state"] = self.doc_state()          # 同 crop：让宿主的滑块跟着这一笔走
        emit(fr)
        return True

    def _white_balance_controller(self):
        from .white_balance_controller import get_controller
        return get_controller(self, lambda event: emit(event))

    def cmd_white_balance_capture(self, p): self._white_balance_controller().capture.handle(p)

    def cmd_white_balance(self, p):
        self._white_balance_controller().handle(p)

    def _color_picker_controller(self):
        from .color_picker_controller import controller
        return controller(self, lambda event: emit(event))

    def cmd_color_picker_capture(self, p):
        from .id_background_picker import route_capture
        if route_capture(self,p,emit): return
        owner=self.__dict__.get('_colour_editor_capture_owner')
        editor=p.get('picker_action')=='colour_editor' or (owner is not None and owner.capture is not None and owner.capture['descriptor']['capture_id']==p.get('capture_id'))
        if not editor: return self._color_picker_controller().capture.handle(p)
        q={k:v for k,v in p.items() if k not in ('picker_action','picker_channel')}
        q['cmd']='colour_editor_capture';q['request_id']=str(p.get('capture_id',''))+':'+str(p.get('action',''))
        if q.get('action')=='cancel' and 'generation' not in q:
            q['generation']=owner.capture['descriptor']['generation'] if owner is not None and owner.capture is not None else '0'
        try:
            event=self._colour_editor_capture().handle(q)
            event.update(event='color_picker_capture',capture_id=p.get('capture_id'),ticket=p.get('ticket'))
            emit(event)
        except Exception as error:
            emit({'event':'color_picker_capture','action':p.get('action'),'capture_id':p.get('capture_id'),'ticket':p.get('ticket'),'success':False,'error':str(error)[:1000]})
    def cmd_color_picker_probe(self, p): self._color_picker_controller().capture.probe(p)
    def cmd_color_picker(self, p): self._color_picker_controller().handle(p)

    def _levels_controller(self):
        controller = self.__dict__.get("_levels_owner")
        if controller is None:
            controller = LevelsController(LevelsPorts(
                guard=lambda name: self._guard_editable(name),
                document_id=lambda: self._load_id,
                install_pipeline=lambda spec: self._vram.set_levels(spec),
                render_frame=lambda mode: self._write_current_frame(mode),
                status=lambda: self.doc_state()), emit=lambda event: emit(event))
            self._levels_owner = controller
        return controller

    _levels = property(lambda self: self._levels_controller().snapshot(),
        lambda self, value: self._levels_controller().restore_spec(value))

    def cmd_levels(self, p: dict): return self._levels_controller().handle_command(p)

    def _color_capture_controller(self):
        from .color_capture_controller import ColorCaptureController, CapturePorts
        from .color_capture_pipeline import document_context, sample_output
        owner=self.__dict__.get("_color_capture_owner")
        if owner is None:
            owner=ColorCaptureController(CapturePorts(
                document=lambda:document_context(self._load_id,self.shm,self.doc_state()["crop"]),
                guard=lambda:(self._guard_editable("color capture") or
                    ("Release full-resolution inspection before colour sampling" if
                     any(x is not None for x in (self._inspection_controller().tx,self._inspection_controller().result,self._inspection_controller().job)) else None)),
                render=lambda:self._write_current_frame("color_capture"),
                sample=lambda region,dims:sample_output(self._vram,*self._retouch_render_args(),self._params,region,dims)),
                emit=lambda event:emit(event))
            self._color_capture_owner=owner
        return owner

    def cmd_color_capture(self, p: dict): self._color_capture_controller().handle(p)

    def _source_patch_controller(self):
        from .source_patch_controller import get_controller
        return get_controller(self, lambda event: emit(event))

    def _local_mask_controller(self):
        from .local_mask_controller import controller
        return controller(self, emit)

    def cmd_local_masks(self, p): self._local_mask_controller().apply(p)

    def cmd_prompted_masks(self, p):
        from .prompted_mask_controller import controller
        controller(self, emit).handle(p)

    def cmd_source_patch_capture(self, p): self._source_patch_controller().capture.handle(p)

    def cmd_source_patch(self, p): self._source_patch_controller().handle(p)
    def cmd_clone_stamp(self, p): self._source_patch_controller().handle(p)

    def cmd_color_scopes(self, p: dict):
        from .color_scopes_controller import ScopePorts, handle_scopes
        from .color_scopes_sampling import sample_stage
        from .color_scopes_bridge import analyze
        owner=self._inspection_controller()
        busy=lambda: (self._guard_editable("color scopes") or
            ("Full-resolution inspection owns resources; release it before sampling" if
             owner.tx is not None or owner.result is not None or owner.job is not None else None))
        handle_scopes(p,ScopePorts(lambda:self._load_id,busy,
            lambda stage:sample_stage(self._vram,stage,*self._retouch_render_args(),params=self._params),analyze),emit)


    def cmd_curves(self, p: dict):
        success = False
        try:
            success = bool(self._cmd_curves_edit(p))
        finally:
            request = p.get("request_id")
            if not isinstance(request, str) or len(request) > 128:
                request = None
            emit({"event": "curves_result", "request_id": request,
                  "success": success, "document_id": self._load_id,
                  "spec": CURVES.check_curves(self._curves)})

    def _cmd_curves_edit(self, p: dict):
        reason = self._guard_editable("curves")
        if reason:
            emit({"event": "error", "error": reason})
            return
        if set(p) - {"cmd", "action", "spec", "gesture_id", "request_id", "document_id"}:
            emit({"event": "error", "error": "curves 收到未知参数"})
            return
        if "document_id" in p and (not self._load_id or p["document_id"] != self._load_id):
            emit({"event": "error", "error": "curves 文档已切换，请重试"})
            return
        action = p.get("action", "set")
        gesture = p.get("gesture_id", "")
        if action not in ("set", "clear") or not isinstance(gesture, str) or len(gesture) > 128:
            emit({"event": "error", "error": "curves action/gesture_id 非法"})
            return
        previous = CURVES.check_curves(self._curves)
        old_pipeline = (self._vram.curves_spec, self._vram.curves_compiled)
        try:
            if action == "set" and "spec" not in p:
                raise ValueError("curves set requires a complete spec")
            spec = CURVES.check_curves(p.get("spec") if action == "set" else None)
            self._vram.set_curves(spec)
            self._curves = spec
            frame = self._write_current_frame("curves")
        except Exception as error:
            self._curves = previous
            try:
                self._vram.curves_spec, self._vram.curves_compiled = old_pipeline
                emit(self._write_current_frame("curves_rollback"))
            except Exception as rollback:
                emit({"event": "engine_warn", "warn": f"曲线回滚帧失败，请重新导入：{rollback}"})
            emit({"event": "error", "error": f"曲线未提交，已保留上一配方：{error}"})
            return
        frame["doc_state"] = self.doc_state()
        emit(frame)
        return True

    def cmd_hsl(self, p: dict):
        """八色 HSL：按色相分段改「色相 / 饱和度 / 明亮度」。

        为什么不做成前端滤镜：八段窗口是逐像素按颜色算的，前端拿不到代理帧；
        更重要的是它必须与导出走同一份式子（`ops/hsl.py` 的两臂），否则屏幕上
        调好的橙色在导出文件里是另一个值。

        动作只有两个：`set`（给 band + 三个量里的任意几个，部分提交）与 `clear`
        （整层归零，**不动**其他 band 的选择）。量程从引擎事件里报，UI 不抄。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear"):
            emit({"event": "error",
                  "error": f"未知 hsl action: {action}（可用：set/clear）"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝改 HSL：先 bench_stop"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        extra = sorted(set(p) - {"cmd", "action", "band", "dh", "ds", "dl"})
        if extra:
            emit({"event": "error", "error": f"hsl 收到不认识的参数：{', '.join(extra)}"
                  "（可用：band / dh / ds / dl）"})
            return
        prev = tuple(self._hsl)
        if action == "clear":
            st = self._vram.clear_hsl()
            self._hsl = (0.0,) * 24
        else:
            if p.get("band") is None:
                emit({"event": "error", "error": "hsl set 需要 band（0…7，对应"
                      f"{'/'.join(BAND_NAMES)}）"})
                return
            try:
                band = int(p["band"])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"hsl band 不是整数：{p.get('band')!r}"})
                return
            if not 0 <= band < len(BAND_NAMES):
                emit({"event": "error", "error": f"hsl band={band} 越界（0…7）"})
                return
            given = {k: p[k] for k in ("dh", "ds", "dl") if p.get(k) is not None}
            if not given:
                emit({"event": "error", "error": "hsl set 什么也没给：至少给 dh/ds/dl 里一个，"
                      "或者走 clear 把整层关掉"})
                return
            cur = list(self._hsl)
            base = band * 3
            for i, k in enumerate(("dh", "ds", "dl")):
                if k in given:
                    cur[base + i] = given[k]
            try:
                # 部分提交：拖一个滑块不该把同段另外两个抹零，但合出来的 24 个数
                # 必须整组校过（与 exposure 的部分提交同一条）。
                st = self._vram.set_hsl(cur)
            except ValueError as e:
                emit({"event": "error", "error": f"八色 HSL 被拒，整条不生效：{e}"})
                return
            self._hsl = tuple(float(v) for v in st["hsl_bands"])
        try:
            fr = self._write_current_frame("hsl")
        except Exception as e:
            self._hsl = prev
            try:
                if prev == (0.0,) * 24:
                    self._vram.clear_hsl()
                else:
                    self._vram.set_hsl(prev)
                back = self._write_current_frame("hsl")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
                emit({"event": "engine_warn", "warn": "HSL 回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"HSL 渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        fr.setdefault("hsl", {})
        fr["hsl"].update(self._vram.hsl_state())
        fr["doc_state"] = self.doc_state()          # 让宿主的滑块跟着这一笔走
        emit(fr)

    def cmd_grade(self, p: dict):
        from .grade_controller import handle
        return handle(self, p, emit)

    def _pipe_copyin(self, rgba, strength: float, radius: int = DEFAULT_RADIUS,
                     eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN,
                     mid_gain: float = DEFAULT_MID_GAIN,
                     broad_gain: float = DEFAULT_BROAD_GAIN,
                     texture_radius: int = DEFAULT_TEXTURE_RADIUS):
        """逐帧搬运路径（对照组）：CPU numpy → H2D → 内核 → D2H → CPU numpy。

        返回 (RGBA, 各段 ms)。故意不复用输入缓冲：那是 test_frame 的缓存本体，
        改写它会让下一帧的「基图」逐帧漂走，「帧真的在换」这个证据就不可靠了。

        磨皮参数照单接收：两条臂跑同一组参数，否则 copyin 与 resident 的差值里混着算法差异。
        """
        import numpy as np

        from .ops.guided import make_tensor, retouch_t, to_numpy_chw
        from .quant import quantize_np

        seg = dict(pre=0.0, kernel=0.0, cpu_post=0.0)
        out = self._pipe_out
        if out is None or out.shape != rgba.shape:
            out = np.empty_like(rgba)
            out[:, :, 3] = 255
            self._pipe_out = out
        t = monotonic_ns()
        arr = rgba[:, :, :3].astype(np.float32) / 255.0
        tensor = make_tensor(arr, self.device)
        seg["pre"] = (monotonic_ns() - t) / 1e6
        t = monotonic_ns()
        # 这里原先写的是 radius=12, eps=6e-4 两个字面量、而且不传 detail_gain：默认值一改
        # 这条对照臂就会静默漂离开生产参数，两个臂比的就不是同一件事了（M2-a 新加的
        # 三个参数必须一并带过来，否则对照臂还在跑二分频，差值里混着算法改动）
        o = retouch_t(tensor, strength=strength, radius=radius, eps=eps,
                      detail_gain=detail_gain, mid_gain=mid_gain,
                      broad_gain=broad_gain, texture_radius=texture_radius)
        self._sync()
        seg["kernel"] = (monotonic_ns() - t) / 1e6
        t = monotonic_ns()
        # 量化走唯一口径（四舍五入）：这条对照臂与常驻臂必须用同一种收尾，
        # 否则两臂的差值里混着半 LSB 的系统偏移，字节对拍就没法看了
        out[:, :, :3] = quantize_np(to_numpy_chw(o))
        seg["cpu_post"] = (monotonic_ns() - t) / 1e6
        return out, seg

    def _resolve_device(self, want: str) -> str:
        """把 "auto"（出厂默认）落实成 torch 真正认的那一块卡。

        为什么这不是宿主该替它定的事：装机件里没人设 LRT_DEVICE，而宿主当时把默认
        写成了 "cpu"——那一台机器上 torch 是 rocm/cuda 版、卡也在，整条 GPU 管线却
        被绕开了（M8 裸环境那一轮就是在这一句上抓到的：帧率 53 而不是 60，因为会话
        建在 CPU 上）。设备能不能用只有 torch 自己是权威，与 raw_backends /
        matting_backends 同一条理由：能力由引擎报，宿主不猜。

        显式要 "cuda" 而本机没 GPU 依旧保留原字符串（_cuda=False），不静默改写：
        报表上那个 "cuda" 与 cuda:false 并存才是“这块卡没认上”的可诊断形状。
        """
        if want != "auto":
            return want
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception as e:      # torch 缺失就是没 GPU 可用，但不能拖垮切设备
            emit({"event": "engine_warn", "warn": f"设备自动选择时 torch 不可用（落到 cpu）：{e}"})
            return "cpu"

    def cmd_set_device(self, p: dict):
        # 跑靶进行中整条拒绝。原来只拦"重建常驻会话"，可 self.device/self._cuda 在拦截之前
        # 就已经改写并发出了 device_set：会话还留在旧设备上服务，而 _sync() 按 self._cuda
        # 决定要不要 synchronize —— cuda 翻成 cpu 后跑靶线程的 kernel 段只剩"入队时间"，
        # 滤波与混合看起来突然变快，数据不崩但分段计时与设备标签双双失真。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 set_device：先 bench_stop"})
            return
        if self._export is not None and self._export.is_alive():
            # 导出线程里存的是拍的 device；但换设备会重建当前会话并清掉那些图层产物，
            # 正在跑的那一批下一张拿到的就是半旧半新的状态
            emit({"event": "error", "error": "导出进行中，拒绝 set_device：等 export_done"})
            return
        self.device = self._resolve_device(str(p.get("device", "auto") or "auto"))
        # 只有 torch 真认了这个后端才算 GPU，否则 _sync 会去调一个不存在的 API
        self._cuda = False
        if self.device.startswith("cuda"):
            try:
                import torch
                self._torch = torch
                self._cuda = torch.cuda.is_available()
            except Exception as e:
                emit({"event": "engine_warn", "warn": f"torch 不可用: {e}"})
        emit({"event": "device_set", "device": self.device, "cuda": self._cuda})
        # 预热：把 GPU 上下文与首帧内核加载付在起进程时，而不是用户第一次点“导入”时
        # （F 轮：冷首图 ~299 ms vs 稳态 ~35 ms，那 265 ms 与图尺寸无关）。已有会话就不必
        # 再预热：那条链已被真图跑过，再建一个小会话只会白占显存。
        if self._cuda and not self._image_loaded:
            try:
                ms = warm_device(self._effective_device())
            except Exception as e:      # 预热失败不许拖垮设备切换，但必须报出来
                emit({"event": "engine_warn", "warn": f"GPU 预热失败（首图会慢）：{e}"})
                ms = 0.0
            if ms > 0.0:
                emit({"event": "engine_warm", "warm_ms": round(ms, 2), "device": self.device})
        # 已经建好的真图会话必须跟着迁移：不然“切设备”只改了个字符串，旧张量继续在
        # 原设备上服务，而所有上报都按新设备解读。重建代价实测 1.6~1.9 ms。
        if self._image_loaded and self._vram is not None \
                and str(self._vram.device) != self._effective_device():
            if self.bench is not None and self.bench.is_alive():
                # 跑靶中途重建会写花正在用的会话与缓冲，当场拒并说清原因
                emit({"event": "error", "error": "跑靶进行中，不迁移常驻会话：先 bench_stop"})
                return
            self._fence_current_document()
            emit({"event": "engine_info", "info": f"常驻会话从 {self._vram.device} 重建到 {self._effective_device()}"})
            self._attach_pipeline(self._src_rgb)
            # 预计算产物是“这个会话这个设备上的张量”：迁完不重挂，掩膜就停在旧设备上，
            # 下一次带 channel 的渲染会直接读错/读到已释放的显存。切文档也要重挂，
            # 所以这一段抽成了一个函数而不是两份手抄（两份的下场已经受过）。
            if self._precompute is not None:
                self._rehang_precompute(replayed_for="device_switch")
                # 形变层已在 _attach_pipeline 里跟着新会话重解过（那里不补帧，因为
                # 下面紧后就自己渲染并写 shm）——这里不能再解一次，那会把换设备的
                # 一次性成本翻倍，而 deform_builds 会凭空多一格
            if self.shm is not None and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
                # 通道必须跟着会话一起迁移：不传 channel 的话，报表里 active_channel 还是 skin，
                # 而给用户补发的是一帧全图渲染——字段与实际执行不一致正是本仓最贵那个坑的形状
                strength, channel = self._retouch_render_args()
                FABRIC.sync(self); LM.sync(self); LGR.sync(self); MLR.sync(self); SBR.sync(self); OPR.sync(self); SKR.sync(self); LIPR.sync(self); BROWR.sync(self); NOSER.sync(self); EYER.sync(self); MOUTHR.sync(self); self._people_sync(); IDR.sync(self); ERR.sync(self); RCR.sync(self); SCR.sync(self); ETH.sync_current(self); PDH.sync_current(self); CGA.sync(self); SCLA.sync(self); CEA.sync(self); PCA.sync(self)
                CER.render_preview(self) if CER.active(self) else PGR.render_preview(self) if PGR.active(self) else SKR.render_proxy(self,lambda:self._vram.render(strength, channel=channel, **self._params))
                with self._wlock:
                    seq, t_emit, slot = self.shm.write_frame(self._vram.read_back(), presentation=self._frame_presentation())
                emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                      "w": self.shm.w, "h": self.shm.h, "mode": "device_switch", **SKR.proxy_flags(self)})

    # ------------------------------------------------------------ M4 全尺寸导出
    EXPORT_KEYS = {"cmd", "action", "images", "out_dir", "format", "quality", "tile", "target_size",
                   "scale", "sharpen", "upscale_backend", "bit_depth",
                   # d2c 那四格：名字进白名单不等于接通，下面逐条校验完才进 snap
                   "output_profile", "tiff_compression", "metadata_include_gps",
                   "conflict_policy", "watermark", "layout", "document_ids",
                   "destination_policy", "destination_plan_id", "intent_revision", "request_id"}

    def _state_to_export_snap(self,st,**options):
        from .export_snapshot import state_to_export_snap
        return state_to_export_snap(self,st,**options)

    def _export_snap_by_path(self, images, doc, snap) -> dict:
        """命令线程里为批量导出的每一张预解析「该用自己的那份配方」+ for_document（P1-1）。

        · 命中当前文档 → 直接用刚现拍的 snap（含它专属图层）。
        · 命中会话里其它底片条格子 → 用那一格自己的 state 组一份（笔迹/蒙版/裁剪各归各），
          for_document=True 带全它自己的图层。
        · 不在会话里的裸文件路径 → 没有独立编辑状态可用，退回共享参数、for_document=False，
          让 _export_snapshot 逐图 skip 掉文档专属层——与既有口径一致，绝不假装搬了配方。

        全部在命令线程读 self._docs：worker 里不回读 live 字段（并发铁律，与整份 snap
        预拍同一条理由——中途扫盘/切图会改掉 _docs，worker 读到的就不是开工那一刻的配方）。
        """
        out: dict = {}
        for p in images:
            if p == doc:
                out[p] = (snap, True)
                continue
            i = self._index_of(p)
            if 0 <= i < len(self._docs) and isinstance(self._docs[i].get("state"), dict):
                st = self._docs[i]["state"]
                out[p] = (self._state_to_export_snap(
                    st, device=snap["device"], scale=snap["scale"],
                    upscale_backend=snap["upscale_backend"], sharpen=snap["sharpen"], source_path=p), True)
            else:
                out[p] = (snap, False)
        return out

    def _prepare_export_snapshot(self, path: str, snap: dict, for_document: bool):
        """Resolve each image's semantic scope without borrowing another face's mask.

        Only label-based skin edits can be regenerated across bare files. Brush,
        reshape, eye/teeth and background coordinates remain document-specific.
        The copied snapshot never mutates the current document or batch recipe.
        """
        from .creative_document_base import require_rebound_snapshot
        from .export import ExportError
        from .people_export import verify_source as verify_people_source, isolated_snapshot
        verify_people_source(snap,path);snap=isolated_snapshot(snap,for_document=for_document)
        require_rebound_snapshot(snap)
        from .common_background_source import verify_snapshot as verify_common_background
        verify_common_background(snap,path)
        if snap.get("grade_scope") == "objects":
            if not for_document: raise ExportError("Source-bound mask objects cannot transfer to another photo")
            LM.verify_snapshot(snap, path)
        if LGS.has_groups(snap):
            if not for_document: raise ExportError("独立局部调色不能借用其他照片，请先通过目标预检同步")
            LGS.verify_snapshot(snap, path)
        if ERS.check(snap.get("effect_recovery"))["targets"]:
            if not for_document: raise ExportError("恢复笔迹不能借用其他源照片")
            ERR.verify_snapshot(snap, path)
        if MLS.check(snap.get("manual_liquify"))["strokes"]:
            if not for_document: raise ExportError("手动液化笔迹不能借用其他源照片")
            MLR.verify_snapshot(snap, path)
        if SBS.check(snap.get("studio_background"))["source"] is not None:
            if not for_document: raise ExportError("背景范围不能借用其他源照片")
            SBR.verify_snapshot(snap, path)
        if IDS.active(snap.get("id_background")):
            if not for_document: raise ExportError("证件照范围不能借用其他源照片")
            IDR.verify_snapshot(snap,path)
        if SKS.check(snap.get("sky_replacement"))["enabled"]:
            if not for_document: raise ExportError("天空替换必须逐图使用自己的明确区域")
            SKR.verify_snapshot(snap,path)
        if OPS.source_bound(OPS.check(snap.get('optics'))):
            if not for_document: raise ExportError('自动镜头/透视必须逐图匹配或分析，请先用预设/批量同步到目标照片')
            OPR.verify_snapshot(snap,path)
        channel_active = bool(snap.get("channel")) and float(snap.get("strength", 0)) != 0
        grade_active = (str(snap.get("grade_scope", "all")) == "skin"
                        and float(tuple(snap.get("grade", (0, 0, 0, 1)))[3]) != 0
                        and any(float(x) != 0 for x in tuple(snap.get("grade", (0, 0, 0, 1)))[:3]))
        if snap.get('creative_base') is not None:
            if not for_document:raise ExportError('Derived smoothing cannot reuse another target source')
            from .creative_derived_smoothing import verify_snapshot as verify_smoothing
            verify_smoothing(snap,path)
            return snap, for_document  # Never infer derived masks from the physical original.
        if not channel_active and not grade_active:
            return snap, for_document
        def require_skin(pc):
            import numpy as np
            mask = (getattr(pc, "masks", None) or {}).get("skin")
            if mask is None or not np.isfinite(mask).all() or not np.any(np.asarray(mask) > 0):
                raise ExportError("该图片未找到置信度足够的皮肤区域，不能把空蒙版报成已完成皮肤调整")
        if for_document and snap.get("precompute") is not None:
            require_skin(snap["precompute"])
            return snap, for_document
        if channel_active and snap.get("channel") != "skin":
            raise ExportError("该图片缺少所选蒙版，不能用全图处理替代局部作用域")
        if for_document:
            targeted = any(float(x) != 0 for x in ((snap.get("deform") or {}).get("amounts") or {}).values())
            targeted |= LIPS.active(snap.get("lip_makeup")) or BROWS.active(snap.get("brow_shape")) or NOSES.active(snap.get("nose_shape")) or EYES.active(snap.get("eye_shape")) or MOUTHS.active(snap.get("mouth_shape"))
            targeted |= WSTATE.active_enhance((snap.get("enhance") or {}).get("amounts") or {})
            if targeted:
                raise ExportError("人物定向编辑缺少选定关键点，请完成该图片的分析后导出，不能替用户选择人物")
        from .face import MediaPipeFace
        from .decode import load_rgb
        proxy = load_rgb(path, device=snap.get("device"))
        with MediaPipeFace() as backend:
            own_precompute = backend(proxy.rgb)
        require_skin(own_precompute)
        prepared = dict(snap)
        prepared["precompute"] = own_precompute
        if not for_document:
            prepared.update(repair_ops=[], light_ops=[],
                            deform={"amounts": {}, "built": False}, deform_defer=False,
                            enhance={"amounts": {}, "built": False}, enhance_defer=False, _bg={})
            prepared["export_skipped"] = ["文档专属笔迹/形变/眼牙/换底未复制；皮肤蒙版已逐图重新分析"]
            if prepared.get("grade_scope") == "brush":
                prepared.update(grade=(0.0, 0.0, 0.0, 1.0), grade_scope="all", grade_mask=None)
                prepared["export_skipped"].append("另一张图片的局部调色画笔未复制")
        return prepared, True

    def _export_snapshot(self, snap: dict, eh: int, ew: int, *, for_document: bool):
        # One shared evaluator: background inspection must not construct a fake
        # Engine or maintain a second, incomplete interpretation of the recipe.
        from .export_recipe import build_export_spec
        from .creative_document_base import source_shape
        eh, ew = source_shape(snap, (eh, ew))
        return build_export_spec(snap, eh, ew, for_document=for_document)

    def cmd_export_destination(self, p):
        rid = p.get("request_id")
        if not isinstance(rid, str) or not rid or len(rid) > 128:
            emit({"event":"error", "error":"无效目录预览请求身份"}); return
        if p.get("action") == "cancel":
            emit({"event":"export_destination_result", "request_id":rid, "status":"ready", "value":{"cancelled":True}}); return
        try:
            if p.get("action") != "preview" or not isinstance(p.get("export_options"), dict):
                raise ValueError("无效目录预览动作")
            command = {**p["export_options"], "cmd":"export", "action":"preview", "request_id":rid,
                       "destination_policy":p["policy"], "document_ids":p["document_ids"],
                       "intent_revision":p["intent_revision"]}
            self.cmd_export(command)
        except (ValueError,TypeError,KeyError,OSError,RuntimeError) as error:
            emit({"event":"export_destination_result", "request_id":rid, "status":"failed", "error":str(error)})

    def cmd_export(self, p: dict):
        """全尺寸分块导出（批量）。在 worker 线程里跑：满幅一块图就能是几秒。"""
        preview = p.get("action") == "preview"
        def respond(payload):
            if preview and payload.get("event") == "error":
                emit({"event":"export_destination_result", "request_id":p.get("request_id"),
                      "status":"failed", "error":payload.get("error")})
            else: emit(payload)
        unknown = set(p) - self.EXPORT_KEYS
        if unknown:
            respond({"event": "error", "error": f"export 收到不认识的参数：{sorted(unknown)}"})
            return
        # action 在白名单里就必须被校验：不校验的话 {"action":"status"} 会当成"开始导出"
        # 直接跑起来——前端想要的是状态，拿到的是一次满幅批量出片。
        action = p.get("action", "start")
        if action not in ("start", "preview"):
            respond({"event": "error",
                  "error": f"export 只认识 action=start（收到 {action!r}）；" \
                           "进度看 export_progress / export_done 事件"})
            return
        if self.bench is not None and self.bench.is_alive():
            respond({"event": "error", "error": "跑靶进行中，拒绝导出：先 bench_stop"})
            return
        if self._export is not None and self._export.is_alive():
            respond({"event": "error",
                  "error": "导出已在进行中：一批只许一个（两个导出会同抢一块卡，"
                           "峰值账单就不是那个数了）"})
            return
        doc = self._doc_path
        from . import virtual_copy_export as VCX
        try: selected_documents = VCX.select(self, p)
        except ValueError as error:
            respond({"event":"error","error":str(error)}); return
        images = [row['path'] for row in selected_documents]
        if not isinstance(images, list) or not images:
            respond({"event": "error", "error": "export 需要 images（路径列表），且当前没有已加载的文档"})
            return
        if any((not isinstance(x, str) or not x) for x in images):
            respond({"event": "error", "error": "export 的 images 必须是非空字符串列表"})
            return
        # 路径一律按绝对路径比对，但**必须排在校验之后**：先归一会把空字符串变成一个
        # 真实目录、把 "not-a-list" 这个字符串拆成十个单字符路径，于是那两条拒绝双双
        # 失效（本轮就是这么撞出来的：total=10 张图开跑了）。
        # 为什么仍要归一：底片条扫出来的、导出请求里给的、当前文档记的，三者可能是
        # 相对/绝对两种写法；比不上的代价不是报错而是静默——for_document 判假，笔迹与
        # 形变全部不进满幅文件，而事件里写着“已导出”。
        images = [os.path.abspath(x) for x in images]
        out_dir = p.get("out_dir") or (p.get("destination_policy") or {}).get("chosen_root")
        if (p.get("destination_policy") or {}).get("mode") == "source_folder":
            out_dir = os.path.dirname(images[0])
        if not isinstance(out_dir, str) or not out_dir:
            respond({"event": "error", "error": "export 需要 out_dir（导出目录）"})
            return
        out_dir_abs = os.path.abspath(out_dir)
        # 目录创建挪到全部参数校验之后（见下方“建目录”那条）：校验没过就先把用户的
        # 目录建出来，失败的路径会在盘上留下一个空文件夹，而报错说的是“参数不合法”
        fmt = str(p.get("format", "jpg")).lower().lstrip(".")
        if fmt not in FORMATS:
            respond({"event": "error", "error": f"不支持的导出格式：{fmt}（可用 {sorted(set(FORMATS))}）"})
            return
        # 原片只读（CORE-004）：落点不许指向**任何一张输入**。
        # 今天它并不会真的盖掉源文件（resolve_target 对已存在的目标只会 skip_and_report
        # 或 recheck，枚举里根本没有 overwrite），但拿输入目录当输出目录仍然是一种错用：
        # 默认策略下整批会“完成而一个文件也没新写”，而事件里写着跳过——用户看到的是
        # 导出跑了而目录里没有一样新东西。更重要的是：这条不变量不能依赖“今天没有
        # overwrite 策略”——那是一句会被后人改的话，而源文件不可变是一句必须一直真的话。
        collide = VCX.source_collisions(self, selected_documents, out_dir_abs, fmt)
        if collide and p.get("destination_policy") is None:
            respond({"event": "error",
                  "error": "导出目标就是输入文件本身，整批拒绝（原片只读）："
                           + "；".join(collide[:4]) + ("…" if len(collide) > 4 else "")
                           + "；换一个导出目录（同名同格式时 skip_and_report 会整批“跳过”，"
                             "recheck 会写成 -0001 副本，两者都不是用户要的“导出一张”）"})
            return
        try:
            quality = int(p.get("quality", 95))
            tile = int(p.get("tile", DEFAULT_TILE))
        except (TypeError, ValueError):
            respond({"event": "error", "error": "quality/tile 必须是整数"})
            return
        if not (MIN_TILE <= tile <= MAX_TILE):
            respond({"event": "error", "error": f"tile={tile} 越界（允许 {MIN_TILE}~{MAX_TILE}）"})
            return
        if not (1 <= quality <= 100):
            respond({"event": "error", "error": f"quality={quality} 越界（需要 1~100）"})
            return
        # 放大（M7）：这一层只做"能不能解析"的校，参数上下限的唯一口径在
        # ExportSpec.check（与各层 setter 同源），不在这里抄第二份数
        from .ops.upscale import check_scale
        try:
            scale = check_scale(p.get("scale", 1))
        except (ValueError, TypeError) as e:
            respond({"event": "error", "error": f"scale 非法：{e}"})
            return
        backend = str(p.get("upscale_backend", "lanczos3"))
        if backend not in ("lanczos3", "realesrgan"):
            respond({"event": "error", "error": f"未知放大后端：{backend}（可用 lanczos3/realesrgan）"})
            return
        if backend == "realesrgan":
            # 无权重整条拒，不降级成 Lanczos 报"AI 超分"（与 lama/birefnet 同一条规矩）。
            # 理由只有一句出处（export.UPSCALE_NOT_WIRED）：命令层与 ExportSpec 各写一份
            # 就会漂，而“设好 sha256 后重试”那一版把未接入出片环路这一件事推给了权重。
            respond({"event": "error", "error": UPSCALE_NOT_WIRED})
            return
        try:
            sharpen = float(p.get("sharpen", 0.0))
        except (TypeError, ValueError):
            respond({"event": "error", "error": "sharpen 必须是 0~2 的数"})
            return
        # 越界值必须在开跑前就拒：ExportSpec.check 里那一条虽然也会拦，但它跑在
        # worker 里，拦下时 export_progress 已经发出去了——进度条走完后什么都没有，
        # 上一轮 M4 就是为这一件事付过费。界只有一处出处（export 模块常量）。
        if not (math.isfinite(sharpen) and 0.0 <= sharpen <= SHARPEN_AMOUNT_LIMIT):
            respond({"event": "error",
                  "error": f"sharpen={sharpen} 越界（需要 [0,{SHARPEN_AMOUNT_LIMIT}]）"})
            return
        # Native16 source enters neutral passthrough or genuine floating edits;
        # output containers must retain RGB16, never silently become RGB8.
        try:
            bit_depth = int(p.get("bit_depth", 8))
        except (TypeError, ValueError):
            respond({"event": "error", "error": f"bit_depth={p.get('bit_depth')!r} 不是整数（只认 8 或 16）"})
            return
        if bit_depth not in (8, 16):
            respond({"event": "error", "error": f"bit_depth={bit_depth} 不支持（只认 8 或 16）"})
            return
        if bit_depth == 16:
            if fmt not in ("tif", "tiff", "png"):
                respond({"event": "error",
                      "error": f"16-bit 输出支持真实 RGB16 TIFF/PNG（收到 format={fmt}）；"
                               "JPEG/WebP 不支持本路径，不拿降到 8-bit 冒充 16-bit 出片"})
                return
        from .export_target_size_adapter import request_policy
        try:
            target_size = request_policy(p, format=fmt, bit_depth=bit_depth)
        except ValueError as error:
            respond({"event":"error", "error":str(error)})
            return
        # d2c：ICC / 压缩 / 元数据 / 冲突策略。四条都在命令线程里校验完，理由与
        # sharpen 那条一样——worker 里拦下时 export_progress 已经发出去了。
        from .export import ExportError as _ExportError
        from .export import _check_policy, _tiff_compression
        output_profile = str(p.get("output_profile", "srgb"))
        include_gps = p.get("metadata_include_gps", False)
        if not isinstance(include_gps, bool):
            respond({"event": "error",
                  "error": f"metadata_include_gps={include_gps!r} 必须是 true/false"
                           "（注册表里这一格是 boolean，中性 false=默认不外泄 GPS）"})
            return
        if bit_depth == 16 and include_gps:
            respond({"event": "error", "error": "RGB16 TIFF/PNG 暂不透传 EXIF/GPS；请关闭写入 GPS，或选择常规 RGB8 导出"})
            return
        conflict_policy = str(p.get("conflict_policy", "skip_and_report"))
        # Preserve the previous protocol default while accepting explicit lossless
        # compression in both bit depths. Predictor 2 preserves decoded samples.
        tiff_comp = str(p.get("tiff_compression", "none" if bit_depth == 16 and fmt in ("tif", "tiff") else "deflate"))
        try:
            _check_policy(conflict_policy)
            comp_key, _ = _tiff_compression(tiff_comp)
            if output_profile not in ("none", "srgb", "source") and not os.path.isfile(output_profile):
                raise _ExportError(f"output_profile={output_profile!r} 本层不带该档"
                                   "（可用：srgb / source / none，或一个真实的 .icc 文件路径）")
        except _ExportError as e:
            respond({"event": "error", "error": str(e)})
            return
        if fmt not in ("tif", "tiff") and (comp_key != "deflate" or (bit_depth == 16 and "tiff_compression" in p)):
            # 不夹也不忽略：只有 TIFF 读这个值，给 JPEG 设 deflate 是一次无效的输入
            respond({"event": "error",
                  "error": f"tiff_compression={tiff_comp!r} 只对 TIFF 有意义（当前 format={fmt}）："
                           "JPEG/WebP 用 quality；PNG16 固定无损编码，不使用 TIFF 压缩参数"})
            return
        # 参数在命令线程里全部拍定：worker 里不再读 self._*，否则中途改一下滑块，
        # 这一批里前几张与后几张用的就不是同一套设置（而事件里只写了一份）
        snap = self._state_to_export_snap(self._capture_state(),device=self.device,scale=scale,
            upscale_backend=backend,sharpen=sharpen)
        # Validate every frozen per-image recipe, not the active image's live
        # fields. Otherwise a neutral active image silently bypasses edits on
        # another image in a 16-bit passthrough batch.
        try: entry_ids, snap_by_path, export_entries = VCX.freeze(self, selected_documents, snap)
        except (ValueError,RuntimeError,OSError) as error:
            respond({"event":"error","error":str(error)}); return
        from . import watermark as WM
        from .layout_spec import normalize as normalize_layout, LAYOUT_ITEM
        try:
            snap["export_watermark"] = WM.freeze_settings(p.get("watermark"))
            snap["export_layout"] = normalize_layout(p.get("layout"))
        except (ValueError, TypeError, OSError) as error:
            respond({"event": "error", "error": f"水印/排版设置无效：{error}"})
            return
        # Pixel edits are now routed to the float/RGB16 pipeline per image.
        # The neutral classifier remains below to select exact passthrough;
        # it must not be used to silently omit nonneutral frozen recipes.
        # 四格打包成一个 dict：_export_args 已经是第 9 元组，再往中间插
        # 会让“哪一位是什么”只有数位置的人看得懂；加一位 dict 反而把这一批的口径写清了
        # （opts 必须先有名字再进元组：上一版把字面量直接写在元组里，而下面建台账的
        # `**opts` 引的是一个不存在的名字——于是每一次批量导出都在 cmd_export 里 NameError，
        # 而开发 venv 里这批用例全部 skip（没 torch），只有运行时 venv 才响得出来）
        opts = {"target_size": target_size, "output_profile": output_profile, "tiff_compression": tiff_comp,
                "metadata_include_gps": bool(include_gps), "conflict_policy": conflict_policy,
                "watermark": WM.public_settings(snap.get("export_watermark")), "layout": snap.get("export_layout"), "document_entries": export_entries}
        destination_plan = None
        if p.get("destination_policy") is not None:
            from . import export_destination_runtime as EDR
            settings = {"format":fmt, "quality":None if target_size else quality, "tile":tile, "bit_depth":bit_depth,
                        "scale":scale, "sharpen":sharpen, "upscale_backend":backend,
                        **{k:v for k,v in opts.items() if k != "document_entries"}}
            try:
                destination_plan = EDR.build(self, selected_documents, entry_ids, export_entries,
                    settings, p["destination_policy"], p.get("intent_revision", 0))
                if preview:
                    respond({"event":"export_destination_result", "request_id":p.get("request_id"),
                             "status":"ready", "value":destination_plan.payload()})
                    return
                if destination_plan.plan_id != p.get("destination_plan_id"):
                    raise ValueError("导出设置、文档或目标文件已变化，请重新预览导出位置")
                if any(e.disposition == "needs_confirmation" for e in destination_plan.entries):
                    raise ValueError("请在导出设置中选择改名或跳过冲突文件，再重新预览")
                opts["destination_plan"] = destination_plan.payload()
            except (ValueError,TypeError,OSError,KeyError,RuntimeError) as error:
                respond({"event":"error", "error":str(error)}); return
        elif preview:
            respond({"event":"error", "error":"目录预览需要位置策略"}); return
        else:
            try: os.makedirs(out_dir, exist_ok=True)
            except OSError as error:
                respond({"event":"error", "error":f"out_dir 不可用：{error}"}); return
        # P1-1：为这批每一张预解析各自的配方（命令线程读 _docs，worker 不再读 live）。
        self._export_args = (entry_ids, out_dir, fmt, quality, tile, doc, snap, bit_depth,
                             opts, snap_by_path)
        # 台账先建再开工：TASK-001 要“状态转移可审计”，而从 queued 起才有第一步。
        # inputs 是**命令当时那一拍**的快照：TASK-002 的“重试固定输入”全靠它，
        # 而配方快照（snap）只活在会话里——重开后的 retry 必须拒而不是拿现在的
        # 滑块重跑（那就是“静默切换最新配方”，TASK-008 明写着不许）。
        self._task_seq += 1
        task = T.new_task("export",
                          {"images": list(images), "out_dir": out_dir, "format": fmt,
                           "quality": None if target_size else quality, "tile": tile, "bit_depth": bit_depth,
                           "doc": doc, **opts},
                          entry_ids + ([LAYOUT_ITEM] if snap.get("export_layout") else []), task_id=f"exp{self._task_seq}-{os.getpid()}")
        # `recipe_persisted` 说的是“这份配方快照现在还在不在会话里”，不是“有没有写过
        # 工程文件”：当场建账的批次必然还在（_task_args 刚收过），只有从盘上读回来的
        # 那一份才 False。上一版在这里写死 False，于是重试的门在**本会话内**也是关着
        # 的——TASK-002 要的“失败重试固定输入”当场就实现不了，而单测层（tasks.py）
        # 看不见这道命令面守卫，只有起真进程的端到端用例才会响。
        for item in task["items"]:
            entry = export_entries.get(item["path"], {})
            item.update({key:entry[key] for key in ("document_id","source_asset_id","recipe_version_id","copy_number") if key in entry})
        task["recipe_persisted"] = True
        self._tasks[task["task_id"]] = task
        # 参数快照按 task_id 收：只拿 `self._export_args` （会话里最后那一批）当快照，
        # 重试旧批次时就会拿新批次的配方重跑——那正是 TASK-002 禁止的那件事
        self._task_args[task["task_id"]] = self._export_args
        self._task_ctl = _TaskControl()
        self._export_task = task
        self._emit_task(task, "建账")
        self._export = threading.Thread(target=self._export_loop, daemon=True)
        self._export.start()

    # ------------------------------------------------------------ 批量任务（LNX-P0-TASK）
    TASK_ACTIONS = ("list", "pause", "resume", "cancel", "retry", "delete")
    TASK_KEYS = {"cmd", "action", "task", "scope"}

    def _task_event(self, task: dict, *, note: str = "", **extra) -> dict:
        """task_state 只有一个组装点：队列里每一格读的必须是同一份。"""
        return {"event": "task_state", "task_id": task["task_id"], "kind": task["kind"],
                "state": task["state"], "attempt": int(task["attempt"]),
                "counts": T.counts(task), "batch": T.batch_state(list(self._tasks.values())),
                "persisted": bool(task.get("persisted")),
                "blocked_reason": task.get("blocked_reason"),
                "out_dir": None if task["inputs"].get("destination_plan") else task["inputs"].get("out_dir"),
                "destination_directories": sorted({os.path.dirname(e["target"]) for e in (task["inputs"].get("destination_plan") or {}).get("entries", [])}),
                "updated_ns": task["updated_ns"], "note": note, **extra}

    def _emit_task(self, task: dict, note: str = "", **extra) -> None:
        emit(self._task_event(task, note=note, **extra))

    def _task_boundary(self, task: dict) -> str:
        """安全点：只在条目**之间**。返回 "continue" 或 "stop"。

        TASK-009 的“已进入原子提交的任务完成后维持成功”在这里是靠结构保证的，
        不是靠判据：这一层根本不提供“中断当前条目”的入口。写一个文件中途被叫停
        就会留下一个解不开的半成品——而它在地账上看起来是“已经写了”。
        """
        ctl = self._task_ctl
        if ctl is None:
            return "continue"
        while True:
            if ctl.cancel.is_set():
                return "stop"
            if task["state"] == T.PAUSE_REQUESTED:
                T.transit(task, T.PAUSED, "已到条目边界")
                self._emit_task(task, "边界上暂停")
            if task["state"] == T.PAUSED:
                # 睡着等 resume（不空转吃 CPU），但带超时：取消与“没带控制位就退出”
                # 都得能在这里醒过来，一个死等的 worker 会把整个批次拖成不可取消
                ctl.resume.wait(0.25)
                if not ctl.pause.is_set():
                    ctl.resume.clear()
                continue
            if task["state"] == T.RESUMING:
                T.transit(task, T.RUNNING, "自边界继续")
                self._emit_task(task, "已继续")
            return "continue"

    def _task_item(self, task: dict | None, path: str, rec: dict) -> None:
        """逐条目结局。skipped 不是成功也不是失败（它得单独数得出来）。"""
        if task is None:
            return
        if "error" in rec:
            T.item_result(task, path, "failed", reason=rec["error"],
                          detail={"target_size":rec.get("target_size"), "encoder_quality":rec.get("encoder_quality"), "directory_fsync":rec.get("directory_fsync"), "stage": rec.get("stage"), "outputs":rec.get("outputs",[]), "destination_plan_id":rec.get("destination_plan_id"), "planned_target":rec.get("planned_target")})
        elif rec.get("out_skipped"):
            T.item_result(task, path, "skipped", reason=rec.get("skip_reason"),
                          out=rec.get("out"), detail={"target_size":rec.get("target_size"), "encoder_quality":rec.get("encoder_quality"), "directory_fsync":rec.get("directory_fsync"), "outputs":rec.get("outputs",[]),"destination_plan_id":rec.get("destination_plan_id")})
        else:
            T.item_result(task, path, "succeeded", out=rec.get("out"),
                          detail={"target_size":rec.get("target_size"), "encoder_quality":rec.get("encoder_quality"), "directory_fsync":rec.get("directory_fsync"), "bytes": rec.get("bytes"), "outputs":rec.get("outputs",[]), "renamed_from":rec.get("renamed_from"), "destination_plan_id":rec.get("destination_plan_id"), "layout_usable": not any(o.get("skipped") for o in rec.get("outputs", []) or [] if o.get("path") == rec.get("out"))})
        self._emit_task(task, f"第 {T.counts(task)['succeeded'] + T.counts(task)['failed']} "
                              f"条已定")

    def _task_find(self, p: dict) -> list:
        """按 task 参数取目标：一个 id、"all"，或未给（唯一那条活的）。"""
        want = p.get("task")
        if isinstance(want, str) and want.lower() in ("all", "*"):
            return [t for t in self._tasks.values()]
        if want is not None:
            t = self._tasks.get(str(want))
            if t is None:
                raise T.TaskError(f"没有这条任务：{want!r}（台账里有："
                                  f"{list(self._tasks)[-8:]}）")
            return [t]
        live = [t for t in self._tasks.values() if T.is_live(t)]
        if not live:
            raise T.TaskError("没有进行中的任务：请带 task=<id> 指名一条已结束的批次")
        if len(live) > 1:
            raise T.TaskError(f"有 {len(live)} 条进行中的任务，得指名 task=<id>"
                              "（“默认作用于最后一条”会静默叫停错的那一批）")
        return live

    def _task_worker_is_live(self, t: dict) -> bool:
        """这条批次现在真有 worker 在跑吗（重开后的旧台账不是）。"""
        return (t is self._export_task and self._export is not None
                and self._export.is_alive())

    def cmd_task(self, p: dict):
        """批量队列：暂停 / 继续 / 取消 / 重试 / 列清单 / 删记录。

        铁律沿用 cmd_project：参数先全量校验、事件只有一个组装点、被拒不留半截状态。
        这里的“被拒”多一半来自转移表（tasks.LEGAL）：不在这里重新判“能不能暂停”，
        否则命令面与 worker 会各自长出一套答案。
        """
        unknown = set(p) - self.TASK_KEYS
        if unknown:
            emit({"event": "error", "error": f"task 收到不认识的参数：{sorted(unknown)}"})
            return
        action = p.get("action", "list")
        if action not in self.TASK_ACTIONS:
            emit({"event": "error", "error": f"未知 task action: {action}"
                  f"（可用：{'/'.join(self.TASK_ACTIONS)}，名单在 ready 的 task_actions 里）"})
            return
        if action == "list":
            emit({"event": "task_list", "tasks": [self._task_event(t) for t in self._tasks.values()],
                  "batch": T.batch_state(list(self._tasks.values()))})
            return
        try:
            targets = self._task_find(p)
        except T.TaskError as e:
            emit({"event": "error", "error": str(e)})
            return
        ctl = self._task_ctl
        changed = []
        try:
            for t in targets:
                if action in ("pause", "resume") and not self._task_worker_is_live(t):
                    # 对“现在根本没在跑的那批”说暂停/继续，只能把台账写成一个
                    # 永远醒不过来的状态（RESUMING 而没 worker）：必须拒并说清为什么
                    t["blocked_reason"] = ("这条批次没有正在跑的 worker（重开后的旧台账）："
                                           "重试请先打开那张图，或干脆取消它")
                    raise T.TaskError(t["blocked_reason"])
                if action == "pause":
                    T.request_pause(t)
                    # 先播“用户请求”再推控制位：倒过来就有一条竞态——worker 可能已经跑到
                    # 边界并先播了 paused，于是事件流里 pause_requested 那一格永远看不见，
                    # 而 TASK-006 要的那两步（先请求、到边界才承认）恰恰要靠这两条事件。
                    self._emit_task(t, f"用户 {action}")
                    if ctl is not None and t is self._export_task:
                        ctl.pause.set()
                        ctl.resume.clear()
                elif action == "resume":
                    T.request_resume(t)
                    self._emit_task(t, f"用户 {action}")
                    if ctl is not None and t is self._export_task:
                        ctl.pause.clear()
                        ctl.resume.set()
                elif action == "cancel":
                    if not self._task_worker_is_live(t):
                        # 没 worker 的取消是**记账**：落到 cancelled，别让台账永远停在
                        # paused；也不删任何已落盘的文件与源图（TASK-009）
                        if t["state"] != T.CANCELLING:
                            T.transit(t, T.CANCELLING, "无 worker 的取消（记账）")
                        T.transit(t, T.CANCELLED, "文件原样保留")
                        self._emit_task(t, "取消（记账：文件原样保留）")
                        continue
                    T.request_cancel(t)
                    self._emit_task(t, f"用户 {action}")
                    if ctl is not None and t is self._export_task:
                        # 睡着等的 worker 得能醒过来看到取消；不推一把就是一场死等
                        ctl.pause.clear()
                        ctl.cancel.set()
                        ctl.resume.set()
                elif action == "retry":
                    self._task_retry(t)
                elif action == "delete":
                    # TASK-009 的下半句：删队列记录不删原图也不删已导出的文件
                    self._tasks.pop(t["task_id"], None)
                changed.append(t)
        except T.TaskError as e:
            # 批次里一条没校过就不改其它条：partial 的队列状态比“整批没动”难查得多
            emit({"event": "error", "error": f"task {action} 被整条拒绝（已改的都在同一批里，"
                  f"而这一批没人确认过）：{e}"})
            return
        if action == "delete":
            emit({"event": "task_deleted", "task_id": targets[0]["task_id"],
                  "sources_touched": False, "outputs_touched": False,
                  "files_kept": T.counts(targets[0]),
                  "batch": T.batch_state(list(self._tasks.values()))})
            return
        for t in changed:
            # retry 与 delete 各自有自己的事件（task_deleted / 重试已排队），不在这里
            # 叠第二条；pause/resume/cancel 已在分支里、抢在控制位之前播过了（那里的
            # 时序是判据的一部分），这里再播一条就成了“同一件事两个答案”
            if action not in ("retry", "delete", "pause", "resume", "cancel"):
                self._emit_task(t, f"用户 {action}")

    def _task_retry(self, t: dict) -> None:
        """重试：同一 task_id、attempt+1、输入用当时那份快照。

        从盘上读回来的任务没有配方快照（它只活在会话里）——这里必须**拒**，而不是
        拿现在的滑块重跑：TASK-002 写的是“固定输入”，TASK-008 写的是“不自动重跑
        或切换最新配方”，两句加起来只有拒这一个答案。想重跑请先打开那张图。
        """
        if not t.get("recipe_persisted", False):
            t["blocked_reason"] = ("配方快照只活在本次会话：重开后请打开这张图再重新导出，"
                                   "本版本不拿“现在的滑块”当那次批次重跑")
            raise T.TaskError(t["blocked_reason"])
        if self._export is not None and self._export.is_alive():
            # 一批只许一个：两条 worker 会同抢一块卡，峰值账单就不是那个数了，
            # 而更坑的是它们会互相把对方的 `self._export_args` 抢掉
            raise T.TaskError("已经有一批在跑：先等 export_done 或取消它，再重试")
        args = self._task_args.get(t["task_id"])
        if args is not None and args[8].get("destination_plan"):
            from .export_destination_policy import restore, DestinationError
            try:
                retained = restore(args[8]["destination_plan"])
                persisted = restore(t["inputs"]["destination_plan"])
                if retained.plan_id != persisted.plan_id: raise DestinationError("冻结导出目标不一致")
            except (ValueError,KeyError,TypeError) as error:
                raise T.TaskError(f"目录计划损坏，拒绝重试：{error}") from error
        _task, pend = T.begin_retry(t)
        if args is None:
            t["recipe_persisted"] = False
            raise T.TaskError("这条批次没有配方快照（重启过的旧台账）：请打开那张图重新导出")
        images, out_dir, fmt, quality, tile, doc, snap, bit_depth, opts, snap_by_path = args
        # 只跑没成功的，输入一律取自这条批次自己的快照，不是 live 字段也不是“最后那批”
        self._export_args = ([p for p in images if p in set(pend)], out_dir, fmt, quality,
                             tile, doc, snap, bit_depth, opts, snap_by_path)
        self._task_args[t["task_id"]] = self._export_args
        self._export_task = t
        self._task_ctl = _TaskControl()
        # 不再回 queued：begin_retry 已经把这一步记成 retrying，而转移表里
        # retrying 只许走 running/cancelling/failed。再插一个“排队”会把账打断（上一版就
        # 是这么非法转移响的）；worker 一开工就自己走 retrying → running，那一步合法
        # 而且已经在 _export_loop 里了。
        self._emit_task(t, f"重试已排队（第 {t['attempt']} 次尝试，{len(pend)} 条）")
        self._export = threading.Thread(target=self._export_loop, daemon=True)
        self._export.start()



    def _export_loop(self):
        from .decode import load_full
        from .export_delivery_render import decode_for_delivery8, render_delivery8, check_source_profile
        from .watermark_delivery import export_delivery16
        from .export_target_size_adapter import write_delivery as write_delivery8
        images, out_dir, fmt, quality, tile, doc, snap, bit_depth, opts, snap_by_path = self._export_args
        watermark = snap.get("export_watermark")
        target_ctl = self._task_ctl  # Capture this batch control; never use a newer retry control.
        task = self._export_task
        n = len(images)
        if task is not None and task["state"] != T.RUNNING:
            T.transit(task, T.RUNNING, "worker 开工")
            self._emit_task(task, "开工")
        t0 = monotonic_ns()
        results: list = []
        failed = 0
        stopped = False
        from .virtual_copy_source import verify_entry, verify_decode
        from . import export_destination_runtime as EDR
        destination_plan = opts.get("destination_plan")
        verified_sources = set()
        for idx, entry_id in enumerate(images):
            entry = opts.get("document_entries", {}).get(entry_id, {"path":entry_id})
            path = entry["path"]
            # 安全点只在条目之间：这一句返“停”时，上一张已经原子提交完了
            if task is not None and self._task_boundary(task) == "stop":
                stopped = True
                break
            stage = "decode"
            try:
                image_started = monotonic_ns()
                immutable_stamp = verify_entry(entry, verified_sources)
                snap_i, for_doc_i = snap_by_path.get(entry_id, (snap, path == doc))
                from . import body_pose_render as body_render
                mask_source_stamp = LM.file_stamp(path) if (snap_i.get("_bg") or {}).get("key_recipe") is not None or snap_i.get('body_pose') is not None or snap_i.get("grade_scope") == "objects" or LGS.has_groups(snap_i) or bool(ERS.check(snap_i.get("effect_recovery"))["targets"]) or bool(MLS.check(snap_i.get("manual_liquify"))["strokes"]) or SBS.check(snap_i.get("studio_background"))["source"] is not None or IDS.check(snap_i.get("id_background"))["source"] is not None or OPS.source_bound(OPS.check(snap_i.get("optics"))) or SKS.check(snap_i.get("sky_replacement"))["enabled"] or snap_i.get("creative_sky_context") is not None or snap_i.get("creative_id_background_context") is not None else None
                stage = "semantic_analysis"
                snap_i, for_doc_i = self._prepare_export_snapshot(path, snap_i, for_doc_i)
                analysis_ms = round((monotonic_ns() - image_started) / 1e6, 2)
                if bit_depth == 16:
                    from .export import export_master_16bit, export_edited_16bit
                    out_path = EDR.primary_target(destination_plan, entry_id) if destination_plan else os.path.join(out_dir, entry.get("stem", os.path.splitext(os.path.basename(path))[0]) + (".png" if fmt == "png" else ".tif"))
                    skipped = []
                    common = dict(output_profile=opts["output_profile"],
                                  conflict_policy=opts["conflict_policy"],
                                  metadata_include_gps=opts["metadata_include_gps"],
                                  tiff_compression=opts["tiff_compression"])
                    if watermark or self._master16_snapshot_blockers(snap_i):
                        stage = "decode16"
                        decode_started = monotonic_ns()
                        d = load_full(path, device=snap_i["device"], want_bits=8 if snap_i.get("creative_base") is not None else 16)
                        verify_decode(path, immutable_stamp)
                        LM.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); LGS.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); ERR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); MLR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); SBR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); IDR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); OPR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); SKR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); RCR.verify_export(snap_i,path,(d.h,d.w)); body_render.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); FRR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w))
                        decode_ms = (monotonic_ns() - decode_started) / 1e6
                        spec, skipped = self._export_snapshot(snap_i, d.h, d.w, for_document=for_doc_i)
                        stage = "edit16"
                        render16 = export_delivery16 if watermark else export_edited_16bit
                        wm_args = {"watermark": watermark} if watermark else {}
                        r = EDR.run(destination_plan, entry_id, render16, d, spec, out_path, device=snap_i["device"], tile=tile,
                                               crop_rect=tuple(snap_i.get("crop_rect") or (0, 0, 1, 1)),
                                               rotation_degrees=float(snap_i.get("crop_rotation") or 0),
                                               decode_ms=decode_ms, **wm_args, **common)
                    else:
                        stage = "master16"
                        r = EDR.run(destination_plan, entry_id, export_master_16bit, path, out_path, device=snap_i["device"],
                                               verify_source=lambda: verify_decode(path, immutable_stamp), **common)
                    results.append({"path": path, "out": r["path"], "format": r["format"],
                                    "bits": 16, "source": r["source"],
                                    "w": r["w"], "h": r["h"], "bytes": r["bytes"],
                                    "write_ms": r["write_ms"], "decode_ms": r["decode_ms"],
                                    "readback_ms": r["readback_ms"],
                                    "verification_ms": r["verification_ms"],
                                    "total_ms": round((monotonic_ns() - image_started) / 1e6, 2),
                                    "semantic_analysis_ms": analysis_ms,
                                    # 质量口径的可追溯件（与 8-bit 那一路同名同义）：16-bit 直通
                                    # 不进编码器，encoder_quality 给 None 而不是 0——拿 0 冒充
                                    # “质量 0”会被读成“用户设了最低质量”
                                    "quality_mapping_version": r["quality_mapping_version"],
                                    "encoder_quality": r["encoder_quality"],
                                    # 三个保真读数直接进事件：它们不是调试道具，而是
                                    # “无损”比较针对待写像素，颜色转换可能有意改变源像素。
                                    # 档位与低8位是诊断信息；自然纯色图不能因档位少被判假16-bit。
                                    "readback_max_diff": r["readback_max_diff"],
                                    "levels_per_channel": r["levels_per_channel"],
                                    "low8_nonzero_px": r["low8_nonzero_px"],
                                    # 冲突跳过与 ICC/GPS 的落盘事实：批量清单里“哪几张没写”
                                    # 必须逐张看得见，只在批级别说一句“有跳过”是没法复查的
                                    "out_skipped": bool(r.get("skipped")),
                                    "skip_reason": r.get("reason"),
                                    "renamed_from": r.get("renamed_from"),
                                    "icc_bytes": r.get("icc_bytes"),
                                    "icc_sha256": r.get("icc_sha256"),
                                    "icc_source": r.get("icc_source"),
                                    "icc_readback_matches": r.get("icc_readback_matches"),
                                    "color_converted": r.get("color_converted"),
                                    "color_conversion_ms": r.get("color_conversion_ms"),
                                    "tiff_compression": r.get("tiff_compression"),
                                    "tiff_compression_tag": r.get("tiff_compression_tag"),
                                    "png_compress_level": r.get("png_compress_level"),
                                    "notes": list(r.get("notes", [])),
                                    "gps_written": r.get("gps_written"),
                                    # 仍叫 skipped：UI 那侧按同一个键读两条通路（16-bit 恒空），
                                    # 冲突跳过用 out_skipped，不把两个语义挤进一个键
                                    "pipeline": r.get("pipeline"),
                                    "render_stats": r.get("render_stats"),
                                    "watermark": r.get("watermark"), "outputs": r.get("outputs"),
                                    "skipped": skipped})
                    # 16-bit 那一路也得有逐图进度与台账结局：以前它 continue 得过早，
                    # 既不发 export_progress 也不记条目——于是 RAW 批量导出在进度条上
                    # 是“动都不动”，在批次账上是“跑完了而没人知道跑了哪几张”。
                    EDR.decorate(results[-1], destination_plan, entry_id)
                    results[-1].update({k:entry.get(k) for k in ("document_id","source_asset_id","recipe_version_id","copy_number")})
                    self._task_item(task, entry_id, results[-1])
                    emit({"event": "export_progress", "index": idx, "total": n, "path": path, "document_id":entry.get("document_id"),
                          "ok": True})
                    continue
                d = decode_for_delivery8(path, device=snap_i["device"], creative_base=snap_i.get("creative_base"))
                verify_decode(path, immutable_stamp)
                LM.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); LGS.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); ERR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); MLR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); SBR.check_export_decode(snap_i, path, mask_source_stamp, (d.h, d.w)); IDR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); OPR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); SKR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); RCR.verify_export(snap_i,path,(d.h,d.w)); body_render.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w)); FRR.check_export_decode(snap_i,path,mask_source_stamp,(d.h,d.w))
                stage = "render"
                # P1-1：这一张用它自己那份配方（当前档=现拍 snap；其它档=它存的 state；
                # 裸文件=共享参数且 for_document=False）。批级 export_done 仍读 snap。
                spec, skipped = self._export_snapshot(snap_i, d.h, d.w,
                                                      for_document=for_doc_i)
                stage = "write"
                out_path = EDR.primary_target(destination_plan, entry_id) if destination_plan else os.path.join(out_dir, entry.get("stem", os.path.splitext(os.path.basename(path))[0]) + "." + fmt)
                frame, st = render_delivery8(d, spec, device=snap_i["device"], tile=tile,
                    crop_rect=tuple(snap_i.get("crop_rect") or (0., 0., 1., 1.)),
                    rotation_degrees=float(snap_i.get("crop_rotation") or 0.))
                check_source_profile(d, opts["output_profile"])
                info = EDR.run(destination_plan, entry_id, write_delivery8, frame, out_path, quality=quality, watermark=watermark,
                                  target_size=opts.get("target_size"),
                                  cancelled=lambda: bool(target_ctl and target_ctl.cancel.is_set()),
                                  output_profile=opts["output_profile"],
                                  source_icc=d.source_icc, source_exif=d.source_exif,
                                  metadata_include_gps=opts["metadata_include_gps"],
                                  conflict_policy=opts["conflict_policy"],
                                  tiff_compression=opts["tiff_compression"])
                results.append({"path": path, "out": info["path"], "format": info["format"],
                                "bytes": info["bytes"], "write_ms": info["write_ms"],
                                "target_size": info.get("target_size"), "directory_fsync": info.get("directory_fsync"),
                                # PNG 实际压缩档位（非 PNG 为 None）：这里是从 info 里
                                # 摘键组装的，不补这一笔就会在协议边界上静默丢掉——
                                # quality 95 与文件按哪个档位写的对不上账，批量报表里看不出来
                                "compress_level": info.get("compress_level"),
                                # 质量表版本与真正递给编码器的值（FORMAT-001）：这张清单是
                                # 从 info 里摸键组装的，不补这两笔就会在协议边界上静默丢掉
                                # （与上一轮 compress_level 同一个坑）
                                "quality_mapping_version": info.get("quality_mapping_version"),
                                "encoder_quality": info.get("encoder_quality"),
                                "out_skipped": bool(info.get("skipped")),
                                "skip_reason": info.get("reason"),
                                "renamed_from": info.get("renamed_from"),
                                "icc_bytes": info.get("icc_bytes"),
                                "icc_sha256": info.get("icc_sha256"),
                                "gps_written": info.get("gps_written"),
                                "orientation_dropped": info.get("orientation_dropped"),
                                "tiff_compression": info.get("tiff_compression"),
                                "watermark": info.get("watermark"), "outputs": info.get("outputs"),
                                "skipped": skipped, **st})
            except Exception as e:      # 逐图失败不能带倒整批
                failed += 1
                results.append({"path": path, "stage": stage, "error": f"{type(e).__name__}: {e}",
                                "outputs": getattr(e, "outputs", []), "target_size": getattr(e, "target_size", None)})
            emit({"event": "export_progress", "index": idx, "total": n, "path": path, "document_id":entry.get("document_id"),
                  "ok": "error" not in results[-1]})
            EDR.decorate(results[-1], destination_plan, entry_id)
            results[-1].update({k:entry.get(k) for k in ("document_id","source_asset_id","recipe_version_id","copy_number")})
            self._task_item(task, entry_id, results[-1])
        layout_result = None
        if snap.get("export_layout"):
            from .layout_delivery import finish_layout
            layout_result = finish_layout(self, task, snap["export_layout"], out_dir)
        if task is not None:
            # 收尾状态由条目账算出来，不由“循环跑完了”宣布：部分失败报成 succeeded
            # 就是 TASK-003 拒绝的那种“把失败折成完成”
            c = T.counts(task)
            # P1-7 卡住现场：取消落在最后一张正在写文件的时候，worker 不会再
            # 回到 `_task_boundary`（那个检查只在每次迭代开头看一次），`stopped`
            # 就停在 False。但命令面已经把状态推到 CANCELLING。这里必须以状态
            # 为准，不能因 stopped=False 就宣布 SUCCEEDED——LEGAL[CANCELLING]
            # = (CANCELLED, FAILED)，transit(SUCCEEDED) 会抛 TaskError，批次
            # 卡在 CANCELLING，连 export_done 都发不出去。
            if stopped or task["state"] == T.CANCELLING:
                if task["state"] != T.CANCELLING:
                    T.transit(task, T.CANCELLING, "边界上确认取消")
                T.transit(task, T.CANCELLED, f"{c['pending']} 条未跑，"
                                            f"{c['succeeded']} 条已落盘的文件原样保留")
            elif c["failed"]:
                T.transit(task, T.FAILED, f"{c['failed']} 条失败（逐条见 items）")
            else:
                T.transit(task, T.SUCCEEDED, f"{c['succeeded']} 张已落盘，"
                                            f"{c['skipped']} 张按策略跳过")
            self._emit_task(task, "收尾")
        # cancelled 以台账终态为准（CANCELLING 抢在最后一张写完后才落到
        # CANCELLED，此时 `stopped` 仍是 False）；旧的 bool(stopped) 会把
        # “取消成功”的批次报成 cancelled=false，与 task_state=cancelled 自相矛盾。
        _cancelled_final = (task or {}).get("state") == T.CANCELLED
        emit({"event": "export_done", "total": n, "failed": failed,
              "task_id": (task or {}).get("task_id"),
              "task_state": (task or {}).get("state"),
              "cancelled": _cancelled_final,
              "out_dir": out_dir, "format": fmt, "quality": None if opts.get("target_size") else quality, "tile": tile,
              "bit_depth": bit_depth, "layout_result": layout_result, **opts,
              "scale": int(snap["scale"]), "sharpen": float(snap["sharpen"]),
              # 后端名字只在真做了放大时才报：批级别写"lanczos3"而每张图的账单写 None，
              # 就是在同一件事上给两个答案（没放大时"用了哪个后端"这句话本身不成立）
              "upscale_backend": snap["upscale_backend"] if int(snap["scale"]) > 1 else None,
              "total_ms": round((monotonic_ns() - t0) / 1e6, 1), "images": results})

    def _effective_device(self) -> str:
        """会话真正会落在哪个设备上（要求 cuda 但没 GPU 时是 cpu，不是 cuda）。"""
        if self.device.startswith("cuda") and not self._cuda:
            return "cpu"
        return self.device

    def cmd_shutdown(self, _p: dict):
        recovery = self.__dict__.get("_project_recovery_runtime")
        if recovery is not None: recovery.host.close()
        managed = self.__dict__.get("_managed_import_controller")
        if managed is not None: managed.close()
        package = self.__dict__.get("_project_package_controller")
        if package is not None: package.close()
        relocation = self.__dict__.get('_source_relocation_controller')
        if relocation is not None: relocation.close()
        self.stop_flag.set()
        self._quit = True
        emit({"event": "bye"})

    # ------------------------------------------------------------ 主循环
    # 「引擎认哪些命令」只有这一处名单。以前它是一张手抄的字典，而 test_history 里还
    # 有第二份抄件——本轮加 crop 时两份就漂了（抄件少一条，守卫红）。名字与 cmd_* 一一对应，
    # 所以名单本身就是可校验的：少写一个方法或多写一个名字，都在开工第一帧响，
    # 而不是等到用户发那条命令时回一句"未知命令"。
    # ------------------------------------------------------------ 预设与批量（LNX-P0-PRESET / LNX-P0-BATCH）
    PRESET_ACTIONS = PRS.ACTIONS
    PRESET_KEYS = PRS.LEGACY_KEYS | {"request_id", "document_id"}
    BATCH_ACTIONS = BS.ACTIONS
    BATCH_KEYS = BS.KEYS
    # 冻结件里 conflict_policy 只有这两个值，而两个都是**不覆盖**：没有 overwrite
    # 不是漏写，是 EXPORT-001“无提示不覆盖”的同一条要求（ADR-0003）。
    BATCH_POLICIES = BS.POLICIES

    def _replay_state(self, st: dict, *, mode: str, replayed_for: str, strict_local=False) -> dict:
        """装回一份状态并重建会话，返回那一帧。

        重放逻辑只有一份：这里调的就是 `cmd_history` / 换设备 / 切文档用的那三个原始
        动作（`_apply_state` → `_attach_pipeline` → `_rehang_precompute`），没有第二份
        “按字段把图层搭回去”的代码。抽成函数而不是直接改 cmd_history 的内部，是为了
        不把撤销链的计时与事件形状搅进来——那一条有基准测在盯。
        """
        self._apply_state(st)
        self._attach_pipeline(self._src_rgb, adopt=True)
        if self._precompute is not None:
            self._rehang_precompute(replayed_for=replayed_for)
        if strict_local: LM.sync(self, strict=True); LGR.sync(self, strict=True); MLR.sync(self, strict=True); SBR.sync(self, strict=True); OPR.sync(self, strict=True); SKR.sync(self, strict=True); LIPR.sync(self, strict=True); BROWR.sync(self, strict=True); NOSER.sync(self, strict=True); EYER.sync(self, strict=True); MOUTHR.sync(self, strict=True); self._people_sync(strict=True); IDR.sync(self, strict=True); ERR.sync(self, strict=True); RCR.sync(self, strict=True); SCR.sync(self, strict=True); ETH.sync_current(self); PDH.sync_current(self); CGA.sync(self); SCLA.sync(self); CEA.sync(self); PCA.sync(self)
        if strict_local and not self._people_managed() and (ENH.TEETH.active(self._enhance.get("amounts",{})) or ENH.RED_EYE.active(self._enhance.get("amounts",{})) or ENH.PURIFY.active(self._enhance.get("amounts",{}))) and not self._enhance.get("built"):
            raise ValueError("独立牙齿/祛红眼/眼白净化预设未建立目标人物支持，拒绝静默保存无效果参数")
        return self._write_current_frame(mode)

    def _face_known_single(self, row: dict | None, *, live: bool) -> tuple[str, str]:
        """人像模块的作用面判据（冻结件：lnx.skin.v1 / lnx.blemish.v1 = single_face）。

        返回 `(结论, 原因)`，结论三取值：`ok` / `multi` / `unknown`。`unknown` 不等于
        可以默认放过：一张从没打开过、没做过预计算的图，我们**不知道**它有几张脸，
        把人像参数静默盖上去就是拿“没查”冒充“查过了”。
        """
        pc = self._precompute if live else (row or {}).get("state", {}).get("_precompute")
        if pc is None:
            return "unknown", ("这张图还没做过人脸预计算（没打开过或没跑 precompute），"
                               "无法判定是不是单脸；人像模块预设/同步先不作用它")
        # 预计算产物从工程文件里回来时可能是 dict（而不是 FacePrecompute 对象）：
        # 拿 getattr(x, "num_faces", 1) 读一个 dict 会静默地得到 1，于是
        # “多人照片”被当成“单脸”放行——两种形状都读，读不到就当未知。
        n = pc.get("num_faces") if isinstance(pc, dict) else getattr(pc, "num_faces", None)
        if n is None:
            return "unknown", "预计算记录里没有脸数（旧工程文件或形状变了）：按未知处理，不默认放行"
        if int(n) > 1:
            return "multi", f"画面里探到 {n} 张脸（SCOPE-001）"
        return "ok", ""

    def _guard_editable(self, who: str) -> str | None:
        """编辑类命令的四道公用守卫；不过就给原因，不在各自命令里写四份。"""
        if self.bench is not None and self.bench.is_alive():
            return f"跑靶进行中，拒绝 {who}：先 bench_stop"
        if self._export is not None and self._export.is_alive():
            return f"导出进行中，拒绝 {who}：等 export_done"
        if not self._image_loaded or self._vram is None or self._src_rgb is None:
            return f"尚未 load_image，{who} 没有可作用的活动文档"
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            return f"shm 与会话尺寸不配，拒绝 {who}"
        return None






    # Compatibility aliases; the ledger and sequence have a single owner.
    _batches = property(lambda self: self._batch_controller().ledger,
        lambda self, value: setattr(self._batch_controller(), "ledger", value))
    _batch_seq = property(lambda self: self._batch_controller().sequence,
        lambda self, value: setattr(self._batch_controller(), "sequence", value))
    _sync_last = property(lambda self: self._batch_controller().last_result,
        lambda self, value: setattr(self._batch_controller(), "last_result", value))

    # Engine owns protocol ordering; the controller owns all inspection state.
    SNAPSHOT_TICK_BYTES = 1024 * 1024
    SNAPSHOT_MAX_ASSET_BYTES = 512 * 1024 * 1024

    def _inspection_document(self):
        if not self._image_loaded or self._vram is None or not self._doc_path:
            return None
        return self._doc_path

    def _inspection_controller(self):
        controller = self.__dict__.get("_inspection")
        if controller is None:
            controller = InspectionController(
                document=self._inspection_document,
                proxy_dimensions=lambda: (int(self._vram.h), int(self._vram.w)),
                busy=lambda: ((self.bench is not None and self.bench.is_alive()) or
                              (self._export is not None and self._export.is_alive())),
                capture_snapshot=lambda: self._state_to_export_snap(self._capture_state(),
                    device="cpu", scale=1, upscale_backend="lanczos3", sharpen=0),
                emit=lambda event: emit(event))
            self._inspection = controller
        controller.tick_bytes = self.SNAPSHOT_TICK_BYTES
        controller.max_asset_bytes = self.SNAPSHOT_MAX_ASSET_BYTES
        return controller

    def _snapshot_emit(self, error=None):
        return self._inspection_controller().emit_status(error)

    def _cancel_snapshot(self, reason="invalidated", *, notify=True):
        return self._inspection_controller().cancel(reason, notify=notify)

    def _tick_snapshot(self):
        return self._inspection_controller().tick()

    def _snapshot_pending(self):
        return self._inspection_controller().pending()

    def _finish_inspection_shutdown(self):
        return self._inspection_controller().shutdown()

    def cmd_inspection_snapshot(self, p: dict):
        return self._inspection_controller().handle_command(p)

    # Transitional field aliases keep existing embedding/tests compatible while
    # ensuring there is only one owner. Production dispatch uses controller APIs.
    _inspection_snapshot_tx = property(
        lambda self: self._inspection_controller().tx,
        lambda self, value: setattr(self._inspection_controller(), "tx", value))
    _inspection_snapshot_result = property(
        lambda self: self._inspection_controller().result,
        lambda self, value: setattr(self._inspection_controller(), "result", value))
    _inspection_snapshot_id = property(
        lambda self: self._inspection_controller().request_id,
        lambda self, value: setattr(self._inspection_controller(), "request_id", value))
    _inspection_snapshot_last_id = property(
        lambda self: self._inspection_controller().last_id,
        lambda self, value: setattr(self._inspection_controller(), "last_id", value))
    _inspection_snapshot_state = property(
        lambda self: self._inspection_controller().state,
        lambda self, value: setattr(self._inspection_controller(), "state", value))
    _inspection_snapshot_request = property(
        lambda self: self._inspection_controller().request,
        lambda self, value: setattr(self._inspection_controller(), "request", value))
    _inspection_job = property(
        lambda self: self._inspection_controller().job,
        lambda self, value: setattr(self._inspection_controller(), "job", value))
    _inspection_render_config = property(
        lambda self: self._inspection_controller().render_config,
        lambda self, value: setattr(self._inspection_controller(), "render_config", value))
    _inspection_snapshot_error = property(
        lambda self: self._inspection_controller().error,
        lambda self, value: setattr(self._inspection_controller(), "error", value))

    HANDLED = ("fringe_repair", "fringe_repair_preview", "common_background", "common_background_preview", "common_background_readback", "creative_document", "canvas_guides", "project_recovery", "managed_import", "project_package", "export_destination", "virtual_copy", "source_relocation", "preset_organisation", "colour_editor", "colour_editor_state", "colour_editor_sample", "photo_grain", "photo_grain_state", "photo_detail", "photo_detail_state", "photo_detail_receipt", "primary_calibration", "primary_calibration_state", "selective_colour", "selective_colour_state", "colour_grading", "colour_grading_state", "extended_tone", "extended_tone_state", "extended_tone_receipt", "hello", "hair_colour", "shoulder_shape", "leg_shape", "arm_shape", "waist_shape", "leg_length", "neck_shape", "semantic_colour", "semantic_colour_cancel", "sample_library", "sample_library_cancel", "sky_semantic", "sky_replacement_preview", "optics_preview", "studio_background_preview", "manual_liquify_preview", "effect_recovery_preview", "local_grade_live", "inspection_snapshot", "color_scopes", "color_capture", "source_patch_capture", "prompted_masks", "white_balance_capture", "color_picker_capture", "color_picker_probe", "bench_start", "bench_stop", "set_device", "shutdown",
               "load_image", "set_strength", "precompute", "inpaint", "source_patch", "clone_stamp", "local_masks", "effect_recovery", "manual_liquify", "studio_background", "optics", "sky_replacement", "light",
               "deform", "lut", "custom_lut", "grade", "export", "exposure", "white_balance", "color_picker", "hsl", "curves", "levels", "crop", "background",
               "compare", "session", "project", "task", "history", "preset", "batch",
               # 挑图（LNX-PICK-001）。它不在 EDIT_CMDS 里，所以既不进撤销栈也不打脏标记：
               # 它是读出来的一格旁注，不是一次编辑动作
               "face", "pick",
               # 眼牙增强（LNX-PORTRAIT-009）：它是一次编辑（进撤销栈、打脏标记），所以
               # 两个名单都要有它——上一轮加曝光时只改一边，得到的就是"拖完按撤销纹丝不动
               # 而 UI 一句也不说为什么"（CORE-006 为此专门加了一条用例）
               "enhance", "lip_makeup", "brow_shape", "nose_shape", "eye_shape", "mouth_shape", "people", "hair_colour", "fabric")
    _HANDLED_LAMBDA = ("bench_stop",)      # 唯一不开成 cmd_* 的那条：只是置停止位

    def cmd_canvas_guides(self, p):
        return CGH.handle(self, p, emit)

    def cmd_virtual_copy(self, p):
        from .virtual_copy_host import VirtualCopies
        if not hasattr(self, '_virtual_copy_controller'):
            self._virtual_copy_controller = VirtualCopies(self, emit)
        return self._virtual_copy_controller.handle(p)

    def cmd_project_recovery(self, p):
        from .project_recovery_runtime import owner
        runtime = owner(self, emit)
        if p.get('action') == 'checkpoint':
            try:
                result = runtime.checkpoint(p)
                emit({'event':'project_recovery_result', 'request_id':p.get('request_id'),
                      'project_id':p.get('project_id'), 'action':'checkpoint', 'success':True, **result})
            except Exception as error:
                emit({'event':'project_recovery_result', 'request_id':p.get('request_id'),
                      'project_id':p.get('project_id'), 'action':'checkpoint', 'success':False,
                      'error':str(error)})
            return
        if p.get('action') == 'snapshot':
            if p.get('native_settled') is not True: raise ValueError('缺少宿主回执屏障')
            runtime.native_receipts = p.get('native_receipts', [])
        runtime.host.handle(p)

    def cmd_managed_import(self, p):
        return MIH.handle(self, p, emit)

    def cmd_project_package(self, p):
        from .project_package_host import Packages
        if not hasattr(self, "_project_package_controller"):
            self._project_package_controller = Packages(self, emit, PJ.validate)
        try: return self._project_package_controller.handle(p)
        except Exception as error:
            self._project_package_controller.result(p.get("request_id"), "failed", error=str(error))

    def cmd_source_relocation(self, p):
        SRH.handle(self, p, emit, PJ.validate)

    def _dispatch_table(self) -> dict:
        missing = [n for n in self.HANDLED
                   if n not in self._HANDLED_LAMBDA and not callable(getattr(self, "cmd_" + n, None))]
        assert not missing, f"HANDLED 里这些名字没有对应的 cmd_*（名单与方法漂了）：{missing}"
        t = {}
        for n in self.HANDLED:
            if n in self._HANDLED_LAMBDA:
                t[n] = lambda p: (self.stop_flag.set(), emit({"event": "bench_stopped"}))
            else:
                t[n] = getattr(self, "cmd_" + n)
        return t

    def _process_line(self, line, table):
        line = line.strip()
        if not line:
            return
        request_id = None
        msg = {}; name = ""; dispatch_error = None; recovery_boundary = None
        try:
            msg = json.loads(line)
            request_id = msg.pop("_host_request_id", None)
            name = msg.get("cmd", "")
            fn = table.get(name)
            if fn is None:
                emit({"event": "error", "error": f"未知命令: {name}"})
                return
            if name=='common_background_readback':
                fn(msg); return  # Exact read-only receipt query survives broken pipelines and expired previews.
            from .project_recovery_runtime import begin
            recovery_boundary, fn = begin(self, msg, fn)
            recovery = self.__dict__.get('_project_recovery_runtime')
            if recovery is not None and recovery.host.blocks(name, msg):
                raise ValueError('项目恢复操作进行中，请等待原操作完成')
            managed = self.__dict__.get("_managed_import_controller")
            if managed is not None and managed.blocks(name, msg):
                raise ValueError("导入正在进行或结果待确认，请查询原导入操作")
            package = self.__dict__.get("_project_package_controller")
            if package is not None and package.blocks(name, msg):
                raise ValueError("便携包操作进行中，请等待或取消后查询结果")
            CDH.guard_command(self, name, msg)
            relocation = self.__dict__.get('_source_relocation_controller')
            if name == 'virtual_copy' and relocation is not None:
                with relocation.lock: fn(msg)
                return
            if relocation is not None and relocation.blocks(name, msg):
                reason = '原图重定位仍在进行或结果待确认；请查询原操作，暂不接受其他修改'
                if name == 'preset_organisation':
                    emit({'event': 'preset_organisation_result', 'protocol': 1,
                          'request_id': msg.get('request_id'), 'action': msg.get('action'),
                          'success': False, 'outcome_unknown': False, 'error': reason})
                    return
                raise ValueError(reason)
            if name == 'creative_document' and msg.get('action') == 'state':
                fn(msg); return  # Read-only polling must not revoke capture/edit owners.
            if name in ('project_recovery', 'managed_import', 'project_package', 'source_relocation', 'virtual_copy', 'canvas_guides'):
                fn(msg); return  # Path transactions never enter recipe history/capture invalidation.
            if relocation is not None and name == 'project' and msg.get('action') == 'state':
                with relocation.lock: fn(msg)
                return
            if name == "preset_organisation":
                fn(msg); return  # Catalogue metadata never changes image history or capture fences.
            if name == "session" and msg.get("action") == "query":
                if relocation is not None:
                    with relocation.lock: fn(msg)
                else: fn(msg)
                return  # View-only: do not fence or revoke any edit/capture owner.
            from .creative_transfer_host import inventory_read_only
            if inventory_read_only(msg):
                fn(msg); return  # No edit fence, history or capture invalidation.
            if name == "background" and msg.get("action") in ("id_state","id_sample","id_spill_preview","id_spill_paint_source","id_original_shadow_preview","id_original_shadow_paint_source"):
                from .id_background_controller import controller
                recovery_boundary['started'] = True
                controller(self,emit).handle(msg)
                recovery_boundary['returned'] = True
                return
            from .creative_common_background_host import invalidate_other
            invalidate_other(self,name,msg)
            if name not in ('fringe_repair','fringe_repair_preview','hello') and not (name=='inspection_snapshot' and msg.get('action','status')=='status'):self._fringe_cancel_preview()
            if name not in ('hello','color_picker_capture'):
                id_capture=self.__dict__.get('_id_background_capture_owner')
                if id_capture is not None:id_capture.invalidate()
            self._arm_before_command(msg)
            if name not in ('hello','colour_editor_state','colour_editor_sample','color_picker_capture','color_scopes'):
                editor_capture=self.__dict__.get('_colour_editor_capture_owner')
                if editor_capture is not None: editor_capture.invalidate()
            if name in ('fringe_repair','fringe_repair_preview','colour_editor','colour_editor_state','colour_editor_sample','photo_grain','photo_grain_state','photo_detail','photo_detail_state','photo_detail_receipt','primary_calibration','primary_calibration_state','selective_colour','selective_colour_state','colour_grading','colour_grading_state','extended_tone','extended_tone_state','extended_tone_receipt','shoulder_shape','leg_shape','arm_shape','waist_shape','leg_length','neck_shape','custom_lut','sample_library', 'sample_library_cancel','semantic_colour','semantic_colour_cancel'):
                fn(msg); return
            if name not in ('hello', 'local_grade_live'):
                live_grade = self.__dict__.get('_local_grade_live_owner')
                if live_grade is not None: live_grade.invalidate()
            if name in ("source_patch", "clone_stamp") and not self._source_patch_controller().prepare(msg):
                return  # Receipt/cache replay and rejected proofs never advance the fence.
            if name == "sky_replacement" and not self._sky_replacement_controller().prepare(msg):
                return
            if name == "optics" and not self._optics_controller().prepare(msg):
                return
            if name == "studio_background" and not self._studio_background_controller().prepare(msg):
                return
            if name == "manual_liquify" and not self._manual_liquify_controller().prepare(msg):
                return
            if name == "effect_recovery" and not self._effect_recovery_controller().prepare(msg):
                return
            if name == "local_masks" and not self._local_mask_controller().prepare(msg):
                return
            if name == "white_balance" and not self._white_balance_controller().prepare(msg):
                return  # Pick proof and scalar policy are checked before mutation fencing.
            if name == "color_picker" and not self._color_picker_controller().prepare(msg):
                return  # The exact frozen stage proof and scalar plan precede mutation.
            from .document_versions import fences_current_document
            if name not in ("common_background","fringe_repair") and fences_current_document(name,msg,self.EDIT_CMDS) and not (name=="background" and str(msg.get("action","")).startswith("id_")):
                self._fence_current_document()
            if name not in ("hello", "color_scopes", "color_capture") and not (
                    name=="inspection_snapshot" and msg.get("action","status")=="status"):
                self._color_capture_controller().invalidate()
            if name not in ("hello", "source_patch_capture", "prompted_masks", "effect_recovery_preview", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                owner = self.__dict__.get("_source_patch_owner")
                if owner is not None: owner.capture.invalidate()
                prompted = self.__dict__.get('_prompted_mask_owner')
                if prompted is not None: prompted.cancel()
                recovery = self.__dict__.get('_effect_recovery_preview_owner')
                if recovery is not None: recovery.cancel()
            if name not in ("hello", "sky_semantic", "sky_replacement_preview", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                sky = self.__dict__.get("_sky_replacement_preview_owner")
                if sky is not None: sky.cancel()
                semantic = self.__dict__.get("_sky_semantic_owner")
                if semantic is not None: semantic.close()
            if name not in ("hello", "optics_preview", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action") == "status"):
                optics = self.__dict__.get("_optics_preview_owner")
                if optics is not None: optics.cancel()
            if name not in ("hello", "studio_background_preview", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                studio = self.__dict__.get("_studio_background_preview_owner")
                if studio is not None: studio.cancel()
            if name not in ("hello", "manual_liquify_preview", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                liquify = self.__dict__.get("_manual_liquify_preview_owner")
                if liquify is not None: liquify.cancel()
            if name not in ("hello", "white_balance_capture", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                owner = self.__dict__.get("_white_balance_owner")
                if owner is not None: owner.capture.invalidate()
            if name not in ("hello", "color_picker_capture", "color_picker_probe", "color_scopes") and not (
                    name == "inspection_snapshot" and msg.get("action", "status") == "status"):
                owner = self.__dict__.get("_color_picker_owner")
                if owner is not None: owner.capture.invalidate()
            # The executor cancels before any other known command can mutate
            # source arrays/recipes, including history, load, export and shutdown.
            if name not in ("hello", "inspection_snapshot", "color_scopes", "color_capture", "source_patch_capture", "prompted_masks", "effect_recovery_preview", "manual_liquify_preview", "studio_background_preview", "common_background_preview", "optics_preview", "sky_replacement_preview", "sky_semantic", "white_balance_capture", "color_picker_capture", "color_picker_probe"):
                self._cancel_snapshot("command:" + name)
                heavy = name in ("export", "bench_start") or (name == "task" and msg.get("action") in ("resume", "retry"))
                if heavy and self._inspection_controller().worker_running:
                    reason = "Inspection worker is exiting; heavy work must wait for its lease"
                    if name == "bench_start":
                        self._reject_bench(reason, msg.get("mode", "copy"))
                        return
                    raise ValueError(reason)
            if name=="common_background":
                fn(msg); return  # Controller owns the one history transaction and fence.
            if name=="background" and str(msg.get("action","")).startswith("id_"):
                from .id_background_controller import controller
                recovery_boundary['started'] = True
                controller(self,emit).handle(msg)
                recovery_boundary['returned'] = True
                return
            if name in self.EDIT_CMDS and (name!='hair_colour' or msg.get('action') in HAIR_MUTATIONS):
                # 推送点只在这里这一处（见 EDIT_CMDS 的说明）：执行前抄快照，
                # 执行后比对签名决定占不占一步。异常也记（finally）——半改完的
                # 状态正是最需要一次撤销能修回去的时候。
                self._people_shared_mutation=False
                before = self._history_capture()
                group = self._history_group(name, msg)
                try:
                    fn(msg)
                finally:
                    if not self._people_shared_mutation:self._history_record(group, before, coalesce=not (name in ("hair_colour", "white_balance", "color_picker", "source_patch", "clone_stamp", "local_masks", "effect_recovery", "manual_liquify", "studio_background", "optics", "sky_replacement") or (name == "preset" and msg.get("action") == "apply")))
            else:
                fn(msg)
        except Exception as e:  # 协议层不许因单条消息崩溃
            dispatch_error = f"{type(e).__name__}: {e}"
            emit({"event": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                if dispatch_error and name in ('fringe_repair','fringe_repair_preview'):
                    from .fringe_repair_host import dispatch_rejected as fringe_rejected
                    fringe_rejected(msg,dispatch_error,bool(recovery_boundary and recovery_boundary['started']),emit)
                if dispatch_error and name in ('common_background','common_background_preview'):
                    from .creative_common_background_host import rejected
                    rejected(self,msg,dispatch_error,emit)
                if dispatch_error and name == 'creative_document':
                    CDH.dispatch_rejected(msg, dispatch_error, bool(recovery_boundary and recovery_boundary['started']), emit)
                if dispatch_error and name == 'canvas_guides':
                    CGH.rejected(self, msg, dispatch_error, emit)
                if dispatch_error and name=="project_recovery":
                    emit({'event':'project_recovery_result','request_id':msg.get('request_id'),
                          'project_id':msg.get('project_id'),'action':msg.get('action'),
                          'success':False,'error':dispatch_error})
                if dispatch_error and name=="managed_import":
                    emit({"event":"managed_import_result","request_id":msg.get("request_id"),"status":"failed","error":dispatch_error})
                if dispatch_error and name=="background" and str(msg.get("action","")).startswith("id_"):
                    emit({"event":"id_background_result","protocol":1,"request_id":msg.get("request_id"),"document_id":msg.get("document_id"),"action":msg.get("action"),"success":False,"error":dispatch_error,"outcome_unknown":False,"requires_reload":False})
                if name == "brow_shape" and isinstance(msg, dict): self.finish_brow_shape(msg, dispatch_error)
                if name == "nose_shape" and isinstance(msg, dict): self.finish_nose_shape(msg, dispatch_error)
                if name == "eye_shape" and isinstance(msg, dict): self.finish_eye_shape(msg, dispatch_error)
                if name == "mouth_shape" and isinstance(msg, dict): self.finish_mouth_shape(msg, dispatch_error)
                if name == "people" and isinstance(msg, dict): self.finish_people(msg, dispatch_error)
                if name == "hair_colour" and isinstance(msg, dict): self.finish_hair_colour(msg, dispatch_error)
                if name == "sky_replacement" and isinstance(msg, dict):
                    self._sky_replacement_controller().finish(msg, dispatch_error)
                if name == "optics" and isinstance(msg, dict):
                    self._optics_controller().finish(msg, dispatch_error)
                if name == "studio_background" and isinstance(msg, dict):
                    self._studio_background_controller().finish(msg, dispatch_error)
                if name == "manual_liquify" and isinstance(msg, dict):
                    self._manual_liquify_controller().finish(msg, dispatch_error)
                if name == "effect_recovery" and isinstance(msg, dict):
                    self._effect_recovery_controller().finish(msg, dispatch_error)
                if name == "local_masks" and isinstance(msg, dict):
                    self._local_mask_controller().finish(msg, dispatch_error)
                if name == "color_picker" and isinstance(msg, dict):
                    self._color_picker_controller().finish(msg, dispatch_error)
                if name == "white_balance" and isinstance(msg, dict):
                    self._white_balance_controller().finish(msg, dispatch_error)
                if name == "preset" and isinstance(msg, dict):
                    self._preset_controller().finish(msg, dispatch_error)
                if name in ("source_patch", "clone_stamp") and isinstance(msg, dict):
                    self._source_patch_controller().finish(msg, dispatch_error)
            except Exception as error:
                dispatch_error = str(error)
                emit({"event": "error", "error": f"{name} receipt failed: {error}"})
            finally:
                from .project_recovery_runtime import finish
                finish(self, recovery_boundary, dispatch_error)
                if request_id is not None:
                    emit({"event": "command_done", "request_id": request_id})

    def run(self):
        table = self._dispatch_table()
        # Reader enqueues or sets cancellation Events; editing and ticks stay on this one
        # execution sequence. One queued line bounds read-ahead/backpressure.
        inbox = queue.Queue(maxsize=1)
        reader_stop = threading.Event()
        self._command_inbox = inbox
        # Read the protocol fd, not a blocking TextIOWrapper: a private wakeup
        # pipe lets shutdown stop/join the reader while the parent keeps stdin open.
        try:
            input_fd = sys.stdin.fileno()
            wake_read, wake_write = os.pipe()
        except BaseException:
            self._command_inbox = None
            self._cancel_snapshot("reader_init_failed", notify=False)
            self.stop_flag.set()
            if self.shm:
                self.shm.close()
                self.shm.unlink()
            raise
        sample_host = self._sample_library_host()
        reader = threading.Thread(target=read_commands, name="command-reader",
            args=(input_fd, wake_read, inbox, reader_stop),
            kwargs={"ingress": self._custom_lut_ingress, "on_eof": self._custom_lut_reader_stop})
        try:
            reader.start()
            while not self._quit:
                relocation = self.__dict__.get('_source_relocation_controller')
                managed = self.__dict__.get('_managed_import_controller')
                package = self.__dict__.get('_project_package_controller')
                background_allowed = all(owner is None or not owner.blocks('_owned_tick', {}) for owner in (relocation, managed, package))
                if background_allowed:
                    self._tick_owned_previews()
                try:
                    line = inbox.get_nowait()
                except queue.Empty:
                    if background_allowed and self._snapshot_pending():
                        try:
                            self._tick_snapshot()
                        except Exception as exc:
                            self._inspection_controller().fail_tick(exc)  # no retained traceback
                        if self._inspection_controller().worker_running:
                            time.sleep(.005)  # bounded poll cadence, no busy-spin while rendering
                        continue
                    try:
                        line = inbox.get(timeout=.1)
                    except queue.Empty:
                        continue
                if isinstance(line, dict):
                    emit({"event": "error", "error": "stdin: " + line["read_error"]})
                    break
                if not line:
                    break
                self._process_line(line, table)
        finally:
            recovery = self.__dict__.get('_project_recovery_runtime')
            if recovery is not None: recovery.host.close()
            managed = self.__dict__.get('_managed_import_controller')
            if managed is not None: managed.close()
            package = self.__dict__.get('_project_package_controller')
            if package is not None: package.close()
            relocation = self.__dict__.get('_source_relocation_controller')
            if relocation is not None: relocation.close()
            self._owned_reader_stop()
            reader_stop.set()
            try:
                os.write(wake_write, b"x")
                if reader.ident is not None:
                    reader.join()  # selectable reader is explicitly woken, not abandoned
            finally:
                os.close(wake_read)
                os.close(wake_write)
                self._command_inbox = None
                self._finish_inspection_shutdown()
                self._close_owned_previews(); self._arm_shutdown(); self._semantic_shutdown()
                id_capture=self.__dict__.get('_id_background_capture_owner')
                if id_capture is not None:id_capture.invalidate()
                owner = self.__dict__.get("_white_balance_owner")
                if owner is not None: owner.capture.invalidate()
                owner = self.__dict__.get("_source_patch_owner")
                if owner is not None: owner.capture.invalidate()
                owner = self.__dict__.get("_color_picker_owner")
                if owner is not None: owner.capture.invalidate()
                self.stop_flag.set()
                if self.shm:
                    self.shm.close()
                    self.shm.unlink()


def main():
    from .privacy import require_offline_or_exit
    require_offline_or_exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="default")
    args = ap.parse_args()
    Engine(args.session).run()


if __name__ == "__main__":
    main()
