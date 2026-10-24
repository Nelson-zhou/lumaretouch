# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable decoration intent; neither a retouch nor a source-owned support asset."""
from copy import deepcopy
import math

OP = 'lnx.face_decoration.v1'
KEYS = ('pattern', 'strength')
PATTERNS = (
    'freckle_dust', 'freckle_bridge', 'freckle_constellation',
    'freckle_sunburst', 'freckle_scatter',
    'mole_left_cheek', 'mole_right_cheek', 'mole_pair',
)
REQUIREMENT_ID = 'LNX-REF-PC-32471-C-dd14134407'


def neutral():
    return {'version': 1, 'pattern': PATTERNS[0], 'strength': 0.0}


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', *KEYS}
            or type(value['version']) is not int or value['version'] != 1):
        raise ValueError('面部装饰配方字段或版本无效')
    if type(value['pattern']) is not str or value['pattern'] not in PATTERNS:
        raise ValueError('未知面部装饰图案')
    amount = value['strength']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('面部装饰程度需为 0–1 有限数值；这是本地定义范围')
    return {'version': 1, 'pattern': value['pattern'], 'strength': float(amount)}


def active(value):
    return check(value)['strength'] != 0


def preset(value):
    return check(value)


def patches(value):
    recipe = check(value)
    return [{'operation_id': OP, 'parameter_path': '/' + key,
             'unset': False, 'value': recipe[key]} for key in KEYS]


def validate_graph(state):
    from . import people_state as P
    state = P.check(state)
    for row in state['overrides']:
        if row['operation_id'] == OP:
            key = row['parameter_path'][1:]
            if row['parameter_path'] != '/' + key or key not in KEYS:
                raise ValueError('未知面部装饰参数路径')
            check({**neutral(), key: row['value']})
    return deepcopy(state)


def capability():
    """Loaded ABI readiness plus contract; never a portrait-acceptance assertion."""
    from .face_decoration_native import available
    ready = available()
    contract = {'operation_id': OP, 'requirement_id': REQUIREMENT_ID,
            'pattern_count': 8, 'freckle_count': 5, 'mole_count': 3,
            'strength_range': [0.0, 1.0], 'working_space': 'working-srgb',
            'implementation': 'original-analytic-rust-pixel-area-micro-marks',
            'requires': ['real-478-mediapipe-landmarks', 'face-skin-semantics',
                         'known-and-foreign-face-exclusions', 'decoration-specific-visible-skin-review'],
            'source_only_validation': 'UNRUN',
            'limitations': ['moderately-frontal-visible-faces-only',
                            'not-complete-occlusion-or-per-person-semantic-segmentation',
                            'no-reference-artwork-or-official-pattern-equivalence-claim']}
    return {'face_decoration_protocol': 1,
            'face_decoration_available': ready,
            'face_decoration_reason': None if ready else '面部装饰 Rust 核心未安装或 ABI 不匹配；未用祛斑、模糊或腮红替代',
            'face_decoration_contract': contract}
