"""模块作用域：预设与批量的**唯一出处**（LNX-P0-PRESET / lnx.preset.v1 / lnx.batch.v1.module_scope）。

为什么要有这一层，而不是在 `cmd_preset` 与 `cmd_batch` 里各写一份"哪些参数属于哪个模块"：
这两件事的语义必须完全一致——预设是"把一组模块的参数盖到一张图上"，批量同步是
"把同一组参数盖到多张图上"。分开抄就会漂，而漂的后果是"预设里没有的参数被批量偷偷
同步了"（或反之），用户在画面上看不出来。本仓同一形状的坑已经受过两次（doc_state
里的 crop 被塞进 exposure 的字典、per-image 清单在组装处静默丢键）。

作用域的划分**不自己发明**：按冻结注册表（docs/p0/p0-registry-frozen.json）里那些
operation_id 与 parameter_key 来。名单一致由
`engine/tests/test_scope_registry_agreement.py` 双向守卫（测试读冻结件，运行时读这份
代码——注册表文件不进 deb，所以运行时不能去读它，但"漂移"这件事必须在测试里响）。

两个刻意保守的判断：

1. **`enabled` 不单独存一格**。注册表给了 `lnx.skin.v1.enabled`（neutral false）与
   `strength`（neutral 0.0）两个键，而引擎里磨皮只有一位强度：`strength=0` 就是关。
   真造一个独立开关，就会出现 `enabled=1 且 strength=0` 这种"开着但没作用"的配方，
   而它与 `enabled=0` 在画面上完全一样——两份事实说同一件事时必然有一份会说谎。
   因此这里把 `enabled` 解释成 `strength > 0` 的只读别名（导出参数时给真值，导入时
   `enabled=false` 强制把 strength 归 0）。

2. **像素坐标成立的东西不进作用域**。磨皮半径/肌理那几项是逐点参数（可跨图同步）；
   祛瑕笔迹、修容笔迹、掩膜本体都在**代理档像素坐标**上成立，换一张图就是错的坐标，
   所以它们不在任何模块里能被子集选中（`_drop_proxy_layers` 讲的也是同一件事）。
   注册表里 `lnx.mask.v1`（overlay/feather）本版本没接通：它的 `transferable=False`
   且带原因，预设与批量遇到它就整条拒绝，而不是"静默忽略这一模块"。
"""
from __future__ import annotations

import json
import math
from .ops import curves as CURVES
from .ops import levels as LEVELS
from . import hsl_recipe as HSL_RECIPE
from . import white_balance_recipe as WB
from . import local_grade_layers as LOCAL_GRADE
from . import studio_background_scope as STUDIO
from . import id_background_scope as ID_BACKGROUND
from . import optics_scope as OPTICS, optics_auto_scope as OPTICS_AUTO
from . import reference_color_scope as REFERENCE
from . import facial_wrinkle_scope as WRINKLES
from . import lip_makeup_scope as LIP, eye_light_scope as EYE_LIGHT, blush_makeup_scope as BLUSH, lipstick_scope as LIPSTICK, eyeliner_scope as EYELINER, eyelash_scope as EYELASH, brow_makeup_scope as BROW_MAKEUP, iris_makeup_scope as IRIS
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from . import sky_replacement_scope as SKY
from . import semantic_colour_scope as SEMANTIC
from . import custom_lut_scope as CUSTOM_LUT
from . import extended_tone_scope as EXTENDED_TONE
from . import photo_grain_scope as PHOTO_GRAIN
from . import photo_detail_scope as PHOTO_DETAIL
from . import fringe_repair_scope as FRINGE_REPAIR
from . import colour_grading_scope as COLOUR_GRADING
from . import primary_calibration_scope as PRIMARY_CALIBRATION
from . import selective_colour_scope as SELECTIVE_COLOUR
from . import colour_editor_scope as COLOUR_EDITOR

SCHEMA = "lrt.scope.v1"
PRESET_SCHEMA = "lrt.preset.v1"
PRESET_MAX_BYTES = 48 * 1024 * 1024        # Bounded portable CUBE bytes + parameters; metadata receipts omit embedded bytes.
PRESET_MAX_MODULES = 32

# 冻结注册表里 editable 的那几个 operation_id（写在这里而不是去读文件：见模块 docstring）。
OP_CURVES = "lnx.curves.v1"
OP_LEVELS = "lnx.levels.v1"
OP_HSL = "lnx.hsl.v1"
OP_EXPOSURE = "lnx.exposure.v1"
OP_WHITE_BALANCE = "lnx.white_balance.v1"
OP_CROP = "lnx.crop.v1"
OP_SKIN = "lnx.skin.v1"
OP_BLEMISH = "lnx.blemish.v1"
OP_MASK = "lnx.mask.v1"
OP_LOCAL_GRADE = LOCAL_GRADE.OP

# 每个模块：参数名 → (从文档状态读, 往文档状态写)。状态字典就是 `server._capture_state()`
# 那一份（键名以 `_` 打头），所以"预设作用的"与"底片条存的"是同一份字段，没有第三份表示。
# neutral 值与冻结注册表逐条对齐（测试反查），不在这里写"我觉得的中性"。
NEUTRAL_EV = 0.0
NEUTRAL_TEMP = 0.0
NEUTRAL_TINT = 0.0
NEUTRAL_RECT = (0.0, 0.0, 1.0, 1.0)
NEUTRAL_ROTATION = 0.0
NEUTRAL_STRENGTH = 0.0

# 量程逐条照冻结注册表抄，不拿“看着像的量级”写：这三条曾经在这份文件里同时错两次
# （temperature_shift 写成 ±100而冻结件是 ±2000 K；rect 写成 [-0.5,1.5] 而注册表是
# per_coordinate [0,1] 加 x0<x1/y0<y1）。守卫在
# engine/tests/test_scope_registry_agreement.py::test_hard_ranges_agree_with_the_registry。
RANGE_EV = (-5.0, 5.0)                    # unit=EV
RANGE_TEMP = (-2000.0, 2000.0)            # unit=kelvin_offset
RANGE_TINT = (-1.0, 1.0)                  # unit=normalized
RANGE_ROTATION = (-180.0, 180.0)          # unit=degree
RANGE_STRENGTH = (0.0, 1.0)               # unit=normalized
RANGE_RECT_COORD = (0.0, 1.0)             # per_coordinate_min/max

#: operation_id → 契约。`single_face` 的模块只能作用在"已知只有一张脸"的文档上；
#: `transferable` 决定它能否进 `lnx.batch.v1.module_scope` 与预设。
MODULES: dict[str, dict] = {
    FRINGE_REPAIR.OP: {"params": ("enabled", "strength"), "state_fields": FRINGE_REPAIR.FIELDS,
        "single_face": False, "transferable": True, "cmd": "fringe_repair", "label": "黑白边缘修复",
        "read": FRINGE_REPAIR.params_of, "write": FRINGE_REPAIR.install,
        "why_not": "仅同步启用与程度；每张图独立计算边缘支持，源身份和增减笔迹不复制"},
    PHOTO_DETAIL.OP: {"params": ("recipe",), "state_fields": PHOTO_DETAIL.FIELDS, "single_face": False, "transferable": True, "cmd": "photo_detail", "label": "照片细节（非 AI）", "read": PHOTO_DETAIL.params_of, "write": PHOTO_DETAIL.install},
    COLOUR_GRADING.OP: {"params": ("recipe",), "state_fields": COLOUR_GRADING.FIELDS, "single_face": False, "transferable": True, "cmd": "colour_grading", "label": "颜色分级", "read": COLOUR_GRADING.params_of, "write": COLOUR_GRADING.install},
    PHOTO_GRAIN.OP: {"params": ("recipe",), "state_fields": PHOTO_GRAIN.FIELDS, "single_face": False, "transferable": True, "cmd": "photo_grain", "label": "照片颗粒", "read": PHOTO_GRAIN.params_of, "write": PHOTO_GRAIN.install},
    SELECTIVE_COLOUR.OP: {"params": ("recipe",), "state_fields": SELECTIVE_COLOUR.FIELDS, "single_face": False, "transferable": True, "cmd": "selective_colour", "label": "可选颜色", "read": SELECTIVE_COLOUR.params_of, "write": SELECTIVE_COLOUR.install},
    COLOUR_EDITOR.OP: {"params": ("recipe",), "state_fields": COLOUR_EDITOR.FIELDS, "single_face": False, "transferable": True, "cmd": "colour_editor", "label": "色彩编辑器", "read": COLOUR_EDITOR.params_of, "write": COLOUR_EDITOR.install},
    PRIMARY_CALIBRATION.OP: {"params": ("recipe",), "state_fields": PRIMARY_CALIBRATION.FIELDS, "single_face": False, "transferable": True, "cmd": "primary_calibration", "label": "RGB 原色校准", "read": PRIMARY_CALIBRATION.params_of, "write": PRIMARY_CALIBRATION.install},
    EXTENDED_TONE.OP: {"params": ("recipe",), "state_fields": EXTENDED_TONE.FIELDS, "single_face": False,
        "transferable": True, "cmd": "extended_tone", "label": "扩展影调", "read": EXTENDED_TONE.params_of, "write": EXTENDED_TONE.install},
    SEMANTIC.OP: {"params": ("intent",), "state_fields": SEMANTIC.FIELDS, "single_face": False,
                  "transferable": True, "cmd": "semantic_colour", "read": SEMANTIC.params_of, "write": SEMANTIC.install,
                  "transfer_review": SEMANTIC.REVIEW, "dedicated_transport": "semantic_colour", "why_not": SEMANTIC.REASON},
    BROW.OP: {"params": ("recipe",), "state_fields": BROW.FIELDS, "single_face": True,
              "transferable": True, "cmd": "brow_shape", "read": BROW.params_of, "write": BROW.install,
              "why_not": "仅七项双侧参数；目标重新确认真实人物与可见眉毛，不复制源图身份、网格或蒙版"},
    NOSE.OP: {"params": ("recipe",), "state_fields": NOSE.FIELDS, "single_face": True,
              "transferable": True, "cmd": "nose_shape", "read": NOSE.params_of, "write": NOSE.install,
              "why_not": "仅六项二维参数；目标重新确认真实人物与可见鼻部，不复制源图身份、网格或蒙版"},
    EYE.OP: {"params": ("recipe",), "state_fields": EYE.FIELDS, "single_face": True,
              "transferable": True, "cmd": "eye_shape", "read": EYE.params_of, "write": EYE.install,
              "why_not": "仅十项双侧二维参数；目标重新确认真实人物与可见眼部，不复制源图身份、网格或蒙版"},
    REFERENCE.OP: {"params": ("version","strength","reference"), "label": "参考同场景白平衡/亮度", "single_face": False,
              "transferable": True, "cmd": "batch", "read": REFERENCE.params_of, "write": REFERENCE.install,
              "state_fields": REFERENCE.FIELDS},
    MOUTH.OP: {"params": ("recipe",), "state_fields": MOUTH.FIELDS, "single_face": True,
              "transferable": True, "cmd": "mouth_shape", "read": MOUTH.params_of, "write": MOUTH.install,
              "why_not": "仅九项二维参数；目标重新确认真实人物与可见唇部，不复制源图身份、网格或蒙版"},
    OPTICS_AUTO.OP: {"params": ("request",), "state_fields": OPTICS_AUTO.FIELDS, "single_face": False,
                "transferable": True, "cmd": "optics", "read": OPTICS_AUTO.params_of, "write": OPTICS_AUTO.install,
                "why_not": "逐图重匹配配置与重新解算，含手动数值；必须冻结预检，不复制源图矩阵、配置或引导线"},
    BLUSH.OP: {"params": ("recipe",), "state_fields": BLUSH.FIELDS, "single_face": True,
               "transferable": True, "cmd": "people", "read": BLUSH.params_of, "write": BLUSH.install,
               "why_not": "仅腮红图案、程度和颜色；目标重算真实皮肤支持，不复制人物、蒙版、收藏或恢复笔迹"},
    EYELINER.OP: {"params": ("recipe",), "state_fields": EYELINER.FIELDS, "single_face": True,
               "transferable": True, "cmd": "people", "read": EYELINER.params_of, "write": EYELINER.install,
               "why_not": "仅逐眼眼线素材、程度、颜色与联动；目标需要独立眼睑审核，不复制眼球/眼睑蒙版或恢复笔迹"},
    IRIS.OP: {"params": ("recipe",), "state_fields": IRIS.FIELDS, "single_face": True,
              "transferable": True, "cmd": "people", "read": IRIS.params_of, "write": IRIS.install,
              "why_not": "仅原创美瞳图案及程度；目标须独立虹膜、实测瞳孔和高光审核，不复制支持或恢复笔迹"},
    EYELASH.OP: {"params": ("recipe",), "state_fields": EYELASH.FIELDS, "single_face": True,
               "transferable": True, "cmd": "people", "read": EYELASH.params_of, "write": EYELASH.install,
               "why_not": "仅四部位睫毛素材、程度、颜色及双轴联动；目标须独立根部和延伸区审核，不复制源图支持或恢复笔迹"},
    BROW_MAKEUP.OP: {"params": ("recipe",), "state_fields": BROW_MAKEUP.FIELDS, "single_face": True,
               "transferable": True, "cmd": "people", "read": BROW_MAKEUP.params_of, "write": BROW_MAKEUP.install,
               "why_not": "仅逐眼眉妆素材、程度、颜色与联动；目标需要独立眉毛和额头审核，不复制眼球/眉毛和额头蒙版或恢复笔迹"},
    LIPSTICK.OP: {"params": ("recipe",), "state_fields": LIPSTICK.FIELDS, "single_face": True,
               "transferable": True, "cmd": "people", "read": LIPSTICK.params_of, "write": LIPSTICK.install,
               "why_not": "仅口红图案、程度、颜色和质地；目标须审核真实可见唇部，不复制人物、蒙版、收藏或恢复笔迹"},
    CUSTOM_LUT.OP: {"params": ("asset", "amount"), "state_fields": CUSTOM_LUT.FIELDS, "single_face": False,
                    "transferable": True, "cmd": "lut", "read": CUSTOM_LUT.params_of, "write": CUSTOM_LUT.install,
                    "why_not": "本地 CUBE 原始字节随预设携带，应用于 sRGB 编码；域外输入夹边，浮点输出不截断"},
    EYE_LIGHT.OP: {"params": ("recipe",), "state_fields": EYE_LIGHT.FIELDS, "single_face": True,
                   "transferable": True, "cmd": "people", "read": EYE_LIGHT.params_of, "write": EYE_LIGHT.install,
                   "why_not": "仅眼神光素材参数；目标人物须自行审核可见眼球，绝不复制归属、蒙版或恢复笔迹"},
    LIP.OP: {"params": ("recipe",), "state_fields": LIP.FIELDS, "single_face": True,
             "transferable": True, "cmd": "lip_makeup", "read": LIP.params_of, "write": LIP.install,
             "why_not": "仅三项唇妆参数；目标须有自己的真实人脸与嘴唇可见性，恢复笔迹不复制"},
    WRINKLES.OP: {"params": ("recipe",), "state_fields": WRINKLES.FIELDS, "single_face": True,
                "transferable": True, "cmd": "enhance", "read": WRINKLES.params_of, "write": WRINKLES.install,
                "why_not": "仅区域强度与左右联动状态；目标须有自己的真实单脸与皮肤分析，恢复笔迹不复制"},
    SKY.OP: {"params": ("recipe",), "state_fields": SKY.FIELDS, "single_face": False,
             "transferable": True, "cmd": "sky_replacement", "read": SKY.params_of, "write": SKY.install,
             "why_not": "仅天空素材与参数；目标必须已有自己的天空、人物声明及所需水面/地平线，不复制区域"},
    OPTICS.OP: {"params": ("recipe",), "state_fields": OPTICS.FIELDS, "single_face": False,
                "transferable": True, "cmd": "optics", "read": OPTICS.params_of, "write": OPTICS.install,
                "why_not": "仅手动数值；目标保留自己的镜头配置、自动结果与引导线，改变畸变前须重新分析"},
    ID_BACKGROUND.OP: {"params": ("recipe",), "state_fields": ID_BACKGROUND.FIELDS, "single_face": False,
                "transferable": True, "cmd": "background", "read": ID_BACKGROUND.params_of, "write": ID_BACKGROUND.install,
                "why_not": "仅复制颜色及设计参数；各目标保留独立审核范围，素材模式使用各目标自己的已绑定素材"},
    STUDIO.OP: {"params": ("recipe",), "state_fields": STUDIO.FIELDS, "single_face": False,
                "transferable": True, "cmd": "studio_background", "read": STUDIO.params_of, "write": STUDIO.install,
                "why_not": "只同步强度；目标必须已有自己的背景/地面范围，保护和恢复笔迹不复制"},
    OP_LOCAL_GRADE: {
        "params": ("groups",), "state_fields": LOCAL_GRADE.FIELDS,
        "single_face": False, "transferable": True, "cmd": "local_masks",
        "read": LOCAL_GRADE.params_of, "write": LOCAL_GRADE.install,
        "transfer_review": "independent-local-grade-v1",
    },
    OP_HSL: {
        "params": ("recipe",), "state_fields": ("_hsl",), "single_face": False,
        "transferable": True, "cmd": "hsl",
        "read": lambda st: {"recipe": HSL_RECIPE.from_state(st.get("_hsl", HSL_RECIPE.NEUTRAL))},
        "write": lambda st, p: st.update(_hsl=tuple(HSL_RECIPE.check_recipe(p["recipe"])["bands"])),
    },
    OP_LEVELS: {
        "params": ("recipe",), "state_fields": ("_levels",), "single_face": False,
        "transferable": True, "cmd": "levels",
        "read": lambda st: {"recipe": LEVELS.check_levels(st.get("_levels"))},
        "write": lambda st, p: st.update(_levels=LEVELS.check_levels(p["recipe"])),
    },
    OP_CURVES: {
        "params": ("recipe",), "state_fields": ("_curves",), "single_face": False,
        "transferable": True, "cmd": "curves",
        "read": lambda st: {"recipe": CURVES.check_curves(st.get("_curves"))},
        "write": lambda st, p: st.update(_curves=CURVES.check_curves(p["recipe"])),
    },
    OP_EXPOSURE: {
        "params": ("ev",), "state_fields": ("_exposure",), "single_face": False,
        "transferable": True, "cmd": "exposure",
        "read": lambda st: {"ev": float(st["_exposure"][0])},
        # 曝光层是 7 元组（EV/WB + 影调四项，1.12 起）：模块只写自己那一位，
        # 其余原样带上。上一版这里重建 3 元组，套一次色彩预设就把 _exposure 变短，
        # 下一次重挂 (index 3) 直接 IndexError——预设是 P0 用例，写坏一次就是
        # “点预设 → 引擎报错 → 整张图不可信”。
        "write": lambda st, v: st.update(
            _exposure=(float(v.get("ev", NEUTRAL_EV)), st["_exposure"][1],
                       st["_exposure"][2], st["_exposure"][3], st["_exposure"][4],
                       st["_exposure"][5], st["_exposure"][6])),
    },
    OP_WHITE_BALANCE: {
        "params": ("temperature_shift", "tint_shift", "options"),
        "state_fields": ("_exposure", "_exposure_ref_k", "_wb_options"),
        "single_face": False, "transferable": True, "cmd": "exposure",
        "read": WB.transfer_from_state, "write": WB.apply_transfer,
    },
    OP_CROP: {
        "params": ("rect_normalized", "rotation_degrees"),
        "state_fields": ("_crop_rect", "_crop_rotation"),
        "single_face": False, "transferable": True, "cmd": "crop",
        "read": lambda st: {"rect_normalized": [float(x) for x in st["_crop_rect"]],
                            "rotation_degrees": float(st["_crop_rotation"])},
        "write": lambda st, v: st.update(
            _crop_rect=tuple(float(x) for x in v.get("rect_normalized", NEUTRAL_RECT)),
            _crop_rotation=float(v.get("rotation_degrees", NEUTRAL_ROTATION))),
    },
    OP_SKIN: {
        "params": ("strength", "enabled"), "state_fields": ("_strength",),
        "single_face": True, "transferable": True, "cmd": "set_strength",
        "read": lambda st: {"strength": float(st["_strength"]),
                            "enabled": bool(float(st["_strength"]) > 0.0)},
        "write": lambda st, v: st.update(_strength=_strength_from(v)),
    },
    OP_BLEMISH: {
        "params": ("strength", "enabled"), "state_fields": ("_strength",),
        "single_face": True, "transferable": True, "cmd": "set_strength",
        # 注册表里还有一条 `protect_identity_marks`（保留痣/斑），本版本没有那个通路：
        # 磨皮是高低频整体作用，没有“跳过这一像素”的独立开关。把它当“预设能带的参数”
        # 接进来只会得到一个不动任何像素的勾选框（假控件），所以这里**记账为未建模**，
        # 导入带这一参数的预设时整条拒并给出原因。
        "unmodeled": {"protect_identity_marks":
                      "本版本磨皮没有“保护痣/斑”的独立通路（高低频整体作用），"
                      "这一参数不接受，也不做成不动画面的勾选框"},
        "read": lambda st: {"strength": float(st["_strength"]),
                            "enabled": bool(float(st["_strength"]) > 0.0)},
        "write": lambda st, v: st.update(_strength=_strength_from(v)),
    },
    OP_MASK: {
        "params": ("analysis_enabled", "overlay_visible", "feather"),
        "state_fields": (), "single_face": True, "transferable": False, "cmd": None,
        "why_not": "蒙版叠加/羽化本版本未接通（右侧那一栏显式禁用并写了原因），"
                   "不进预设也不进批量作用域",
        "unmodeled": {k: "未接通：见本模块 why_not" for k in
                      ("analysis_enabled", "overlay_visible", "feather")},
        "read": lambda st: {},
        "write": lambda st, v: None,
    },
}

#: 磨皮与祛瑕在引擎里共用同一位强度（注册表把这条写进了 reason：两个"强度"必须同含义）。
#: 因此一份预设/一次批量里同时出现这两个模块时，它们的 strength 必须相等，否则整条拒。
SHARED_STRENGTH_OPS = (OP_SKIN, OP_BLEMISH)


def _strength_from(params: dict) -> float:
    """按 `enabled` 读法把参数折成引擎那一位强度。"""
    s = float(params.get("strength", NEUTRAL_STRENGTH))
    if "enabled" in params and not bool(params["enabled"]):
        s = 0.0
    return s


def known_ops() -> tuple[str, ...]:
    return tuple(MODULES)


def transferable_ops() -> tuple[str, ...]:
    return tuple(op for op, m in MODULES.items() if m["transferable"])


def describe() -> list[dict]:
    """给宿主与报表看的模块表（UI 不抄第二份名单，理由同 doc_state 里的量程）。"""
    out = []
    for op, m in MODULES.items():
        out.append({"operation_id": op, "params": list(m["params"]),
                    "transferable": m["transferable"], "single_face": m["single_face"],
                    "unmodeled": dict(m.get("unmodeled") or {}),
                    "reason": m.get("why_not")})
        if m.get("transfer_review"): out[-1]["transfer_review"] = m["transfer_review"]
        if m.get("dedicated_transport"):out[-1]["dedicated_transport"]=m["dedicated_transport"]
    return out


def unmodeled_reason(op: str, key: str) -> str | None:
    """注册表有、而本版本没建模的那个参数，它的“为什么”（没有记录就回 None）。"""
    return (MODULES.get(op, {}).get("unmodeled") or {}).get(key)


class ScopeError(ValueError):
    """作用域/参数不合法：整条拒绝，绝不"忽略这一模块继续做"。"""


def _finite(value, where: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ScopeError(f"{where} 不是数：{value!r}") from None
    if not math.isfinite(v):
        raise ScopeError(f"{where} 不是有限数：{value!r}")
    return v


def check_params(op: str, params: dict) -> dict:
    """校验一个模块的参数并返回干净副本（未给的键回冻结中性值；旧 WB options 缺省保留目标参考白）。

    未知键**整条拒**：预设文件里多出一个键，要么是别的版本写的（schema 该拦），要么是
    有人想把参数塞进它不属于的模块。静默忽略就是"导入后参数少了一半而没人知道"。
    """
    m = MODULES.get(op)
    if m is None:
        raise ScopeError(f"未知模块 {op!r}（可用：{', '.join(known_ops())}）")
    if not m["transferable"]:
        raise ScopeError(f"{op} 不可作用：{m.get('why_not')}")
    if not isinstance(params, dict):
        raise ScopeError(f"{op} 的参数必须是对象，得到 {type(params).__name__}")
    unknown = sorted(set(params) - set(m["params"]))
    if unknown:
        # 分开报错：“注册表里有而我们没建模”与“从未听过的键”是两件不同的事，
        # 前者要能说出“为什么没接通”（绝不留无响应控件），后者才是笔误。
        parts = [f"{k}：{unmodeled_reason(op, k)}" if unmodeled_reason(op, k) else f"{k}（未知参数）"
                 for k in unknown]
        raise ScopeError(f"{op} 收到不可作用的参数：" + "；".join(parts))
    if op == SEMANTIC.OP:return SEMANTIC.check_params(params)
    if op == SKY.OP:
        try: return SKY.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == REFERENCE.OP: return REFERENCE.check_params(params)
    if op == OPTICS_AUTO.OP:
        try: return OPTICS_AUTO.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == BROW.OP:
        try: return BROW.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == NOSE.OP:
        try: return NOSE.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == EYE.OP:
        try: return EYE.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == MOUTH.OP:
        try: return MOUTH.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == BLUSH.OP:
        try: return BLUSH.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == EYELINER.OP:
        try: return EYELINER.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == IRIS.OP:
        try: return IRIS.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == EYELASH.OP:
        try: return EYELASH.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == BROW_MAKEUP.OP:
        try: return BROW_MAKEUP.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == LIPSTICK.OP:
        try: return LIPSTICK.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == FRINGE_REPAIR.OP:
        try: return FRINGE_REPAIR.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == PHOTO_GRAIN.OP:
        try: return PHOTO_GRAIN.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == COLOUR_GRADING.OP:
        try: return COLOUR_GRADING.check_params(params)
        except ValueError as exc: raise ScopeError(str(exc)) from exc
    if op == PRIMARY_CALIBRATION.OP:
        try: return PRIMARY_CALIBRATION.check_params(params)
        except (ValueError,RuntimeError,OSError) as exc: raise ScopeError(str(exc)) from exc
    if op == COLOUR_EDITOR.OP:
        try: return COLOUR_EDITOR.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == SELECTIVE_COLOUR.OP:
        try: return SELECTIVE_COLOUR.check_params(params)
        except ValueError as exc: raise ScopeError(str(exc)) from exc
    if op == PHOTO_DETAIL.OP:
        try: return PHOTO_DETAIL.check_params(params)
        except ValueError as e: raise ScopeError(str(e)) from e
    if op == EXTENDED_TONE.OP:
        try: return EXTENDED_TONE.check_params(params)
        except ValueError as exc: raise ScopeError(str(exc)) from exc
    if op == CUSTOM_LUT.OP:
        try: return CUSTOM_LUT.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == EYE_LIGHT.OP:
        try: return EYE_LIGHT.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == LIP.OP:
        try: return LIP.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == WRINKLES.OP:
        try: return WRINKLES.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OPTICS.OP:
        try: return OPTICS.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == ID_BACKGROUND.OP:
        try: return ID_BACKGROUND.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == STUDIO.OP:
        try: return STUDIO.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OP_LOCAL_GRADE:
        try: return LOCAL_GRADE.check_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OP_WHITE_BALANCE:
        try: return WB.check_transfer_params(params)
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OP_HSL:
        try: return {"recipe": HSL_RECIPE.check_recipe(params.get("recipe"))}
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OP_LEVELS:
        try: return {"recipe": LEVELS.check_levels(params.get("recipe"))}
        except ValueError as error: raise ScopeError(str(error)) from error
    if op == OP_CURVES:
        try:
            return {"recipe": CURVES.check_curves(params.get("recipe"))}
        except ValueError as error:
            raise ScopeError(str(error)) from error
    out: dict = {}
    for key in m["params"]:
        if key == "enabled":
            if key in params:
                if not isinstance(params[key], bool):
                    raise ScopeError(f"{op}.enabled 必须是布尔，得到 {params[key]!r}")
                out[key] = bool(params[key])
            continue
        if key == "rect_normalized":
            rect = params.get(key, list(NEUTRAL_RECT))
            if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                raise ScopeError(f"{op}.rect_normalized 需要 4 个数，得到 {rect!r}")
            vals = [_finite(x, f"{op}.rect_normalized") for x in rect]
            lo, hi = RANGE_RECT_COORD
            if any(v < lo or v > hi for v in vals):
                raise ScopeError(f"{op}.rect_normalized 越界（归一化坐标逐轴限 [{lo}, {hi}]）：{vals}")
            if vals[2] <= vals[0] or vals[3] <= vals[1]:
                raise ScopeError(f"{op}.rect_normalized 不满足 x0<x1 且 y0<y1：{vals}")
            out[key] = vals
            continue
        lo, hi = {"ev": RANGE_EV, "temperature_shift": RANGE_TEMP, "tint_shift": RANGE_TINT,
                  "rotation_degrees": RANGE_ROTATION, "strength": RANGE_STRENGTH}[key]
        v = _finite(params.get(key, _neutral_of(op, key)), f"{op}.{key}")
        if not lo <= v <= hi:
            raise ScopeError(f"{op}.{key}={v} 超出范围 [{lo}, {hi}]")
        out[key] = v
    return out


def _neutral_of(op: str, key: str):
    if op == FRINGE_REPAIR.OP: return FRINGE_REPAIR.S.neutral()[key]
    if op == PHOTO_GRAIN.OP and key == "recipe": return PHOTO_GRAIN.S.neutral()
    if op == COLOUR_GRADING.OP and key == "recipe": return COLOUR_GRADING.S.neutral()
    if op == PRIMARY_CALIBRATION.OP and key == "recipe": return PRIMARY_CALIBRATION.S.neutral()
    if op == COLOUR_EDITOR.OP and key == "recipe": return COLOUR_EDITOR.S.neutral()
    if op == SELECTIVE_COLOUR.OP and key == "recipe": return SELECTIVE_COLOUR.S.neutral()
    if op == PHOTO_DETAIL.OP and key == "recipe": return PHOTO_DETAIL.S.default()
    if op == EXTENDED_TONE.OP and key == "recipe": return EXTENDED_TONE.S.default()
    if op == OP_WHITE_BALANCE and key == "options": return WB.neutral_transfer_options()
    if op == OP_HSL and key == "recipe": return HSL_RECIPE.default_recipe()
    if op == OP_LEVELS and key == "recipe": return LEVELS.default_levels()
    if op == OP_CURVES and key == "recipe":
        return CURVES.default_curves()
    return {OP_EXPOSURE: {"ev": NEUTRAL_EV},
            OP_WHITE_BALANCE: {"temperature_shift": NEUTRAL_TEMP, "tint_shift": NEUTRAL_TINT},
            OP_CROP: {"rect_normalized": list(NEUTRAL_RECT), "rotation_degrees": NEUTRAL_ROTATION},
            OP_SKIN: {"strength": NEUTRAL_STRENGTH},
            OP_BLEMISH: {"strength": NEUTRAL_STRENGTH}}[op][key]


def params_of(state: dict, ops) -> dict[str, dict]:
    """从一份文档状态里读出这些模块当前的参数（预设在界面上显示"覆盖前是什么"要用）。"""
    return {op: MODULES[op]["read"](state) for op in ops}


def check_scope(ops) -> list[str]:
    """校验 module_scope：非空、已知、可转移，且去重后保序。

    冻结件写得很明白：`module_scope` 的中性值是空集，而**空集不允许通过 preflight**——
    把空集解释成"全部模块"就等于"用户什么都没选，我们把整张配方全盖上去了"。
    """
    if isinstance(ops, str):
        raise ScopeError(f"module_scope 必须是模块名列表，得到字符串 {ops!r}")
    if not ops:
        raise ScopeError("module_scope 不能为空：空集不等于全部模块（冻结件 lnx.batch.v1 的原文）")
    out: list[str] = []
    for op in ops:
        if op not in MODULES:
            raise ScopeError(f"module_scope 里有未知模块 {op!r}（可用：{', '.join(known_ops())}）")
        if not MODULES[op]["transferable"]:
            raise ScopeError(f"module_scope 里有不可作用的模块 {op!r}：{MODULES[op].get('why_not')}")
        if op not in out:
            out.append(op)
    if OPTICS.OP in out and OPTICS_AUTO.OP in out: raise ScopeError("镜头/透视手动保留模式与自动重算模式不能同时选择")
    _check_shared_strength(out, {})
    return out


def _check_shared_strength(ops: list[str], mods: dict[str, dict]) -> None:
    """磨皮与祛瑕同时出现时，那位共享强度必须给同一个数（或干脆不给）。"""
    present = [op for op in SHARED_STRENGTH_OPS if op in ops]
    if len(present) < 2:
        return
    values = set()
    for op in present:
        p = mods.get(op) or {}
        if "strength" in p:
            values.add(round(float(p["strength"]), 9))
        if "enabled" in p and not bool(p["enabled"]):
            values.add(0.0)
    if len(values) > 1:
        raise ScopeError(f"{OP_SKIN} 与 {OP_BLEMISH} 共用同一位磨皮强度，不能给两个值：{sorted(values)}"
                         "（冻结件：两个「强度」必须同一个含义）")


# This is a deliberately separate, closed admission set, not the much broader
# transferable registry. Source/semantic/support consumers need their own ports.
# Crop admission requires the batch/preset owner's frozen full-target visual
# review. This parameter validator alone never authorizes a transfer commit.
DERIVED_PARAMETER_OPS = frozenset((
    OP_EXPOSURE, OP_WHITE_BALANCE, OP_LEVELS, OP_CURVES, OP_HSL,
    EXTENDED_TONE.OP, PHOTO_DETAIL.OP, PHOTO_GRAIN.OP, COLOUR_GRADING.OP, FRINGE_REPAIR.OP,
    PRIMARY_CALIBRATION.OP, SELECTIVE_COLOUR.OP, COLOUR_EDITOR.OP, OP_CROP,
))


def check_derived_modules(mods):
    """Admit actual parameters only; neutral unsupported modules still reject."""
    if type(mods) is not dict or not mods or any(type(op) is not str for op in mods):
        raise ScopeError('合成来源的参数迁移需要明确的非空模块对象')
    denied = set(mods) - DERIVED_PARAMETER_OPS
    if denied:
        raise ScopeError('合成来源的通用预设/批量仅支持全局参数；这些模块须使用独立来源审核通路：' + ', '.join(sorted(denied)))
    check_scope(list(mods))
    clean = {op: check_params(op, params) for op, params in mods.items()}
    if COLOUR_EDITOR.OP in clean and clean[COLOUR_EDITOR.OP]['recipe']['scope'] != 'all':
        raise ScopeError('合成来源的色彩编辑器参数迁移仅支持完整 scope=all 配方，不能复制局部蒙版作用域')
    return clean


def apply_modules(state: dict, mods: dict[str, dict], *, local_replace_legacy=False) -> dict:
    """把 {operation_id: 参数} 盖到一份文档状态上，返回**新的一份**。

    同模块覆盖语义（PRESET-001）：预设里出现的那个模块，参数是**整模块替换**——预设里
    没写的键回到冻结中性值；旧 WB options 缺省保留目标参考白。其它键不保留目标原值。这正是"先套人像预设再套色彩
    预设"能预期重放的原因：两次套完的结果与目标图原来有什么无关（作用域内）。
    """
    from .creative_derived_transfer import require_modules
    mods = require_modules(state, mods)
    ops = list(mods)
    check_scope(ops)
    _check_shared_strength(ops, mods)
    out = dict(state)
    for op in ops:
        clean = check_params(op, mods[op])
        MODULES[op]["write"](out, clean)
    if OP_LOCAL_GRADE in ops and local_replace_legacy: LOCAL_GRADE.clear_legacy(out)
    # 磨皮那位共用强度：两个模块都出现时，后一次 write 不该把前一次的解释推翻掉
    if all(op in ops for op in SHARED_STRENGTH_OPS):
        s = _strength_from(mods[OP_SKIN] if OP_SKIN in mods else mods[OP_BLEMISH])
        out["_strength"] = s
    return out


def restore_modules(current, previous, ops):
    """Restore reviewed target state, including nonportable coverage on undo."""
    from .creative_derived_transfer import involved, require_modules
    if involved(current, related_states=(previous,)):
        # Check the scope before reading unsupported snapshot consumers. Both
        # snapshots participate even when the live row is currently original.
        if set(ops) - DERIVED_PARAMETER_OPS:
            raise ScopeError('合成来源的通用历史不能恢复未经支持的模块')
        require_modules(current, params_of(previous, ops), related_states=(previous,))
    ordinary = [op for op in ops if op not in (OP_LOCAL_GRADE,OPTICS_AUTO.OP,REFERENCE.OP,SEMANTIC.OP,ID_BACKGROUND.OP,FRINGE_REPAIR.OP)]
    result = apply_modules(current, params_of(previous, ordinary)) if ordinary else dict(current)
    if OP_LOCAL_GRADE in ops: LOCAL_GRADE.restore(result, previous)
    if OPTICS_AUTO.OP in ops: OPTICS_AUTO.restore(result, previous)
    if REFERENCE.OP in ops: REFERENCE.restore(result, previous)
    if SEMANTIC.OP in ops: SEMANTIC.restore(result, previous)
    if ID_BACKGROUND.OP in ops: ID_BACKGROUND.restore(result, previous)
    if FRINGE_REPAIR.OP in ops: FRINGE_REPAIR.restore(result, previous)
    return result


# ------------------------------------------------------------------ 预设文件
def validate_preset(doc, *, builtin: bool = False) -> dict:
    """预设文件的静态检查（PRESET-002：恶意输入必须安全拒绝）。

    这一层只做**结构**判断，落盘路径由 `preset_dir` 那一层管（这里根本不碰文件系统）：
    ① schema 版本不认识 → 拒（不"尽力解析新版"：新版字段含义变了而按旧版解释，会得到
       一份看起来正常而作用域错了的配方）；
    ② 名字必须是安全 slug（不许 `/`、`..`、绝对路径、空、超长）——预设名会被拼进
       落盘文件名，这就是路径穿越的入口；
    ③ 模块名单只认 frozen registry 那一组（未知模块整条拒，不静默丢）；
    ④ 每个模块的参数逐条校验（NaN/Inf/越界/类型错都拒）；
    ⑤ 顶层多余键拒；`script`/`code`/`exec` 这一类键名一律拒（我们从不执行预设里的
       任何东西，所以也不接受"看起来能被执行"的内容混进来）；
    ⑥ `builtin` **不是文件里的字段**，而是由调用方（`preset_store` 知道哪个目录是随包的）
       注进去的判定：文件能自报“我是内置的”，就能靠这个名字遮住真内置预设或绕开
       “内置不许删”的守卫。
    """
    if not isinstance(doc, dict):
        raise ScopeError(f"预设必须是 JSON 对象，得到 {type(doc).__name__}")
    if doc.get("schema") != PRESET_SCHEMA:
        raise ScopeError(f"预设 schema 不认识：{doc.get('schema')!r}（本版本只认 {PRESET_SCHEMA!r}）")
    for bad in ("script", "code", "exec", "eval", "command", "python"):
        if bad in doc:
            raise ScopeError(f"预设里出现了 {bad!r} 键：预设只是参数，引擎不执行任何内容")
    if "builtin" in doc:
        raise ScopeError("预设文件里不许自报 builtin：内置与否由引擎按目录判定"
                         "（文件能假扮内置，就能遮住真内置预设与绕开“内置不删”）")
    unknown = sorted(set(doc) - {"schema", "id", "name", "kind", "modules", "author", "note"})
    if unknown:
        raise ScopeError(f"预设里有不认识的顶层键：{unknown}")
    pid = safe_slug(doc.get("id") or doc.get("name"), field="id")
    name = str(doc.get("name") or pid)[:80]
    mods = doc.get("modules")
    if not isinstance(mods, dict) or not mods:
        raise ScopeError("预设的 modules 必须是非空对象：空预设等于「什么都不改」的控件，"
                         "那是假滑块")
    if len(mods) > PRESET_MAX_MODULES:
        raise ScopeError(f"预设的模块数超过上限 {PRESET_MAX_MODULES}：{len(mods)}")
    kinds = {"portrait", "color", "look", "crop", "custom"}
    kind = doc.get("kind") or "custom"
    if kind not in kinds:
        raise ScopeError(f"预设 kind 未知：{kind!r}（可用：{', '.join(sorted(kinds))}）")
    clean: dict[str, dict] = {}
    for op, params in mods.items():
        if op==SEMANTIC.OP:raise ScopeError(SEMANTIC.REASON)
        clean[op] = check_params(op, params or {})
        if op == OP_LOCAL_GRADE:
            try: LOCAL_GRADE.portable(clean[op]['groups'])
            except ValueError as error: raise ScopeError(str(error)) from error
    check_scope(list(clean))
    _check_shared_strength(list(clean), clean)
    return {"schema": PRESET_SCHEMA, "id": pid, "name": name, "kind": kind,
            "modules": clean, "author": str(doc.get("author") or "")[:80],
            "note": str(doc.get("note") or "")[:200], "builtin": bool(builtin)}


def safe_slug(value, *, field: str = "id") -> str:
    """预设 id 的净化：只留 `[a-z0-9._-]`，且不许 `..`、不许以 `.` 开头、长度 1..64。

    这个值会被拼成用户预设目录里的文件名，所以它就是路径穿越的入口。判据不靠
    "看起来正常"：任何需要被转义的字符我们都不接受，而不是"转义后存下来"——转义规则
    一旦与读取侧不一致，就会出现"存进去的名字与找得到的名字不是同一个"。
    """
    raw = str(value or "")
    if not raw.strip():
        raise ScopeError(f"预设的 {field} 不能为空")
    if len(raw) > 64:
        raise ScopeError(f"预设的 {field} 过长（>{64}）：{raw[:20]}…")
    if raw != raw.strip() or any(c in raw for c in ("/", "\\", "\x00")):
        raise ScopeError(f"预设的 {field} 含路径字符或首尾空白：{raw!r}")
    if raw.startswith(".") or ".." in raw:
        raise ScopeError(f"预设的 {field} 不许以 . 开头或含 ..（路径穿越）：{raw!r}")
    if not all(("a" <= c <= "z") or ("0" <= c <= "9") or c in "._-" for c in raw):
        raise ScopeError(f"预设的 {field} 只能用小写字母、数字、._-：{raw!r}")
    return raw


def dump_preset(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
