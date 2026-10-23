"""Portable enhancement scalars, never source masks, FaceRefs or render caches.

This is a view of the existing lnx.enhance.v1 amounts, not a second owner.
The independent tooth and flash red-eye controls use a local [0,1] scale and
neutral zero; the source handbook publishes neither a numerical range nor a
numerical default. Red-eye is a scalar, not a source-derived pupil mask.
"""
from copy import deepcopy
import math
from . import people_algorithms as A, facial_wrinkle_state as W
from . import creative_derived_source as SOURCE
from .ops import enhance as H

OP = A.ENHANCE
FIELDS = ('_enhance', '_enhance_defer')


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'}:
        raise ValueError('眼牙增强预设仅接受参数配方')
    recipe = raw['recipe']
    if (type(recipe) is not dict or set(recipe) != {'version', 'amounts'}
            or type(recipe['version']) is not int or recipe['version'] != 1
            or type(recipe['amounts']) is not dict):
        raise ValueError('眼牙增强预设字段或版本无效；不接受人物、蒙版或修正缓存')
    if any(type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value)
           for value in recipe['amounts'].values()):
        raise ValueError('眼牙增强预设强度必须是 [0,1] 有限数值')
    # Partial old recipes remain neutral for newly introduced controls. Whole
    # module replacement is the existing scope contract, not a sparse UI edit.
    return {'recipe': {'version': 1, 'amounts': A.check_enhance(recipe['amounts'])}}


def amounts_of(state):
    """Validate the complete legacy mirror, then separate the canonical owners."""
    current = state.get('_enhance')
    if current is None:
        current = {}
    if type(current) is not dict:
        raise ValueError('眼牙增强文档状态无效')
    checked = H.check_amounts(current.get('amounts', {}))
    return A.check_enhance({key: value for key, value in checked.items() if key not in W.INTENT_KEYS})


def params_of(state):
    return {'recipe': {'version': 1, 'amounts': amounts_of(state)}}


def install(state, params):
    values = check_params(params)['recipe']['amounts']
    # Generic scope transfer has no effective-source portrait review port.
    # Derived photographs must use the existing confirmed-face parameter path;
    # an original-file precompute or face box cannot authorize this installer.
    if SOURCE.record(state) is not None:
        raise ValueError('合成来源的眼牙增强请使用已审核人物参数映射，不能复用原图人物分析')
    current = deepcopy(state.get('_enhance') or {'amounts': {}, 'built': False, 'box': None})
    H.check_amounts(current.get('amounts', {}))
    current['amounts'] = {**current.get('amounts', {}), **values}
    active = W.active_enhance(current['amounts'])
    box = None
    if active:
        pc = state.get('_precompute')
        if pc is None or getattr(pc, 'backend', None) != 'mediapipe':
            raise ValueError('目标照片须先完成真实人物分析；只同步参数，不复制源照片的人脸或蒙版')
        H._landmark_pixels(getattr(pc, 'landmarks', None), 1, 1)
        if getattr(pc, 'num_faces', 1) != 1 and not state.get('_face_explicit'):
            raise ValueError('目标照片有多个人物，请明确选中人物后应用眼牙增强')
        target = state.get('_face_box')
        if (type(target) not in (list, tuple) or len(target) != 4
                or any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v) for v in target)
                or not (0 <= target[0] < target[2] <= 1 and 0 <= target[1] < target[3] <= 1)):
            raise ValueError('眼牙增强预设需要目标照片自己的明确人物范围')
        box = tuple(round(float(value), 5) for value in target)
    # The destination's other enhancement owner (wrinkles) remains intact.
    # Always rebuild active support from this target, including transitions from
    # combined legacy whitening to either independent tooth colour control, and
    # flash red-eye edits. No source eye support is transferred with the scalar.
    current['built'], current['box'] = False, box
    state['_enhance'], state['_enhance_defer'] = current, active
