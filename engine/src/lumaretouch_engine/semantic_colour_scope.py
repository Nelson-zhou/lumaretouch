# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable reference intent only; generic recipe copying is never an apply path."""
from copy import deepcopy
from . import semantic_colour_state as S,semantic_colour_portable as P
OP=S.OP
FIELDS=(S.KEY,'_semantic_colour_bundle','_semantic_colour_mask_assets')
REVIEW='semantic-colour-target-recompute-v1'
REASON='请在 AI 语义追色的批量/便携预设面板逐目标重新拟合并审核；纯文本模块预设不能暗中省略完整样片，也不能复制来源拟合参数或蒙版。'


def check_params(value):
    if type(value) is not dict or set(value)!={'intent'}:raise ValueError('语义追色作用域仅携带明确的便携意图')
    return {'intent':P.check(value['intent'])}


def params_of(state):return {'intent':P.extract(state.get(S.KEY))}


def install(state,params):
    check_params(params)
    raise ValueError(REASON)


def restore(state,previous):
    from .semantic_colour_project import validate_decoded
    recipe=S.check(previous.get(S.KEY));values={S.KEY:recipe,FIELDS[1]:previous.get(FIELDS[1]),FIELDS[2]:previous.get(FIELDS[2],{})}
    validate_decoded(values);state.update(values)
