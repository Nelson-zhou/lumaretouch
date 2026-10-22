"""Portable strengths only; target-owned analysis and recovery are never copied."""
from copy import deepcopy
from . import facial_wrinkle_state as S
from .facial_wrinkle_runtime import skin_support, landmarks_identity
OP = 'lnx.facial_wrinkles.v1'
FIELDS = ('_enhance', '_enhance_defer')


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'}:
        raise ValueError('面部祛纹预设仅接受参数配方')
    recipe = raw['recipe']
    if (type(recipe) is not dict or set(recipe) != {'version', 'amounts'}
            or type(recipe['version']) is not int or recipe['version'] != 1
            or type(recipe['amounts']) is not dict or set(recipe['amounts']) != set(S.INTENT_KEYS)):
        raise ValueError('面部祛纹预设字段或版本无效；不接受人脸、蒙版或修正缓存')
    return {'recipe': {'version': 1, 'amounts': S.check(recipe['amounts'])}}


def params_of(state):
    return {'recipe': {'version': 1, 'amounts': S.preset((state.get('_enhance') or {}).get('amounts') or {})}}


def install(state, params):
    values = check_params(params)['recipe']['amounts']
    pc = state.get('_precompute')
    if S.active(values):
        if pc is None or getattr(pc, 'backend', None) != 'mediapipe' or skin_support(pc) is None:
            raise ValueError('目标照片须先完成真实人物与皮肤分析；只同步参数，不能复制源照片的人脸或皮肤蒙版')
        landmarks_identity(pc.landmarks)
        # Batch preflight's single_face gate remains authoritative. A standalone
        # preset may use an explicitly selected person, never a guessed first face.
        if getattr(pc, 'num_faces', 1) != 1 and not state.get('_face_explicit'):
            raise ValueError('目标照片有多个人物，请明确选中人物后应用面部祛纹')
    current = deepcopy(state.get('_enhance') or {'amounts': {}, 'built': False, 'box': None})
    current['amounts'] = {**current['amounts'], **values}
    # Keep every existing non-wrinkle control and the target's face binding.
    # Replay rebuilds the selected target's own source-derived field.
    if S.active_enhance(current['amounts']):
        current['built'] = False
        box = state.get('_face_box')
        current['box'] = tuple(round(float(v), 5) for v in box) if box and len(box) == 4 else None
        state['_enhance_defer'] = True
    else:
        current['built'], current['box'] = False, None
        state['_enhance_defer'] = False
    state['_enhance'] = current
