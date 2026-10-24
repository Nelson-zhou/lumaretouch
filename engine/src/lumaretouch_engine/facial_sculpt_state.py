# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable broad facial structure intent only. AUTHORED / UNRUN."""
import math
OP = OPERATION = 'lnx.facial_sculpt.v1'
KEYS = ('highlight', 'shadow')
CONTROL_IDS = {'highlight': 'LNX-REF-PC-32471-C-8f773e9125',
               'shadow': 'LNX-REF-PC-32471-C-01b2ee2d32'}
POLICY = 'reviewed-source-two-scale-facial-log-structure-v1'


def neutral():
    return {'version': 1, 'highlight': 0.0, 'shadow': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('高光/阴影立体配方仅接受版本与两项强度，不接收皮肤、源图或审核')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('不支持此面部立体配方版本')
    for key in KEYS:
        amount = value[key]
        if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
            raise ValueError('面部立体强度必须为 [0,1] 有限数值')
    return {'version': 1, **{key: float(value[key]) for key in KEYS}}


def active(value):
    return any(check(value)[key] != 0 for key in KEYS)


def capability():
    from .facial_sculpt_native import available
    ready = available()
    return {'facial_sculpt_protocol': 1, 'facial_sculpt_available': ready,
            'facial_sculpt_reason': None if ready else '面部立体专用 Rust 内核不可用；未以曝光、光泽或磨皮替代'}


def preset(value):
    return check(value)


def validate_graph(state):
    from .facial_sculpt_project import validate_graph as validate
    return validate(state)


def patches(value):
    recipe = check(value)
    return [{'operation_id': OP, 'parameter_path': '/' + key, 'unset': False,
             'value': recipe[key]} for key in KEYS]
