"""Selected-face ownership for facial_wrinkles and lip_makeup recovery targets.

Whole-photo recovery records remain unchanged. Face-bound records must retain
actual source + 478×3 landmark identity, not an unstable detected-face index.
A new detection of the same person is not automatically authorized as identical.
"""
from copy import deepcopy
import re
from .facial_wrinkle_runtime import landmarks_identity
from . import local_mask_state as M
TARGET = 'facial_wrinkles'
FACE_TARGETS = frozenset(('facial_wrinkles', 'lip_makeup', 'eye_light', 'blush_makeup','lipstick'))


def check_owner(value):
    if (type(value) is not dict or set(value) != {'version', 'source_sha256', 'landmarks_sha256', 'backend'}
            or type(value['version']) is not int or value['version'] != 1 or value['backend'] != 'mediapipe'
            or any(type(value[k]) is not str or not re.fullmatch('[0-9a-f]{64}', value[k])
                   for k in ('source_sha256', 'landmarks_sha256'))):
        raise ValueError('人物局部恢复缺少真实源图与选中人物身份；旧序号不能补造身份')
    return deepcopy(value)


def owner(source, pc):
    if source is None or pc is None or getattr(pc, 'backend', None) != 'mediapipe':
        raise ValueError('请先选定真实人物，再绘制人物局部恢复笔迹')
    return check_owner({'version': 1, 'source_sha256': source['sha256'],
                        'landmarks_sha256': landmarks_identity(pc.landmarks), 'backend': pc.backend})


def current_owner(engine):
    return owner(M.bind_source(engine), engine._precompute)


def check_row(row, source):
    """Call inside recovery-state validation. No added field for other targets."""
    if row['target'] not in FACE_TARGETS:
        if 'owner' in row: raise ValueError('非人物局部恢复不接受人脸归属字段')
        return
    identity = check_owner(row.get('owner'))
    if source is None or identity['source_sha256'] != source['sha256']:
        raise ValueError('人物局部恢复人物不属于本源照片')


def verify(value, source, pc, *, target=None):
    names = FACE_TARGETS if target is None else {target}
    rows = [row for row in value['targets'] if row['target'] in names and row['enabled']]
    if not rows: return
    actual = owner(source, pc)
    for row in rows:
        if check_owner(row.get('owner')) != actual:
            raise ValueError('人物局部恢复的人物已改变或关键点已重新检测；该效果已暂停，请返回原人物或清除本目标恢复笔迹')


def identity_key(pc):
    if pc is None or getattr(pc, 'backend', None) != 'mediapipe': return None
    try: return landmarks_identity(pc.landmarks)
    except ValueError: return None


def suspend_only_target(stage, value, source, pc):
    """Prepare all valid other operators; do not convert face mismatch to global failure.

    Shared EffectRecoveryStage owns the per-target suspension dictionary and
    consults it before blending this family. Export calls verify directly and
    fails instead of exporting a silently suspended requested correction.
    """
    for name in FACE_TARGETS:
        try:
            verify(value, source, pc, target=name)
        except ValueError as error:
            stage.suspended_targets[name] = str(error)


def availability(pipe):
    delta = getattr(pipe, 'facial_wrinkle_delta', None) if pipe else None
    suspended = getattr(getattr(pipe, 'effect_recovery', None), 'suspended_targets', {}).get(TARGET) if pipe else None
    return {'active': bool(delta is not None and delta.any() and not suspended),
            'reason': suspended or (None if delta is not None and bool(delta.any()) else '请先启用选中人物的面部祛纹；本笔只恢复这一个功能族')}
