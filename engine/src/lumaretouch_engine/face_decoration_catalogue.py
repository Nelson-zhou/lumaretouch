# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable original analytic materials; no external artwork or mutable seeds."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .face_decoration_state import PATTERNS

CATALOGUE_SHA256 = '414200ac138b5f75986db42b95c12ac77b5142816bc6a00f391287090956cf56'


def catalogue():
    raw = Path(__file__).with_name('face_decoration_patterns.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOGUE_SHA256:
        raise ValueError('面部装饰素材目录损坏或版本改变，未替换已保存效果')
    value = json.loads(raw)
    if (value['version'] != 1 or tuple(row['id'] for row in value['patterns']) != PATTERNS
            or [row['kind'] for row in value['patterns']] != ['freckle'] * 5 + ['mole'] * 3):
        raise ValueError('面部装饰素材身份不匹配')
    for row in value['patterns']:
        if not 1 <= len(row['marks']) <= 64:
            raise ValueError('面部装饰素材数量超出预算')
        for mark in row['marks']:
            if (len(mark) != 7 or any(type(v) not in (int, float) or not math.isfinite(v) for v in mark)
                    or any(abs(v) > 2 for v in mark[:2])
                    or not .002 <= mark[2] <= .06 or not .002 <= mark[3] <= .06
                    or not 0 < mark[5] <= 1):
                raise ValueError('面部装饰微点参数无效')
    return deepcopy(value)


def material(pattern):
    if pattern not in PATTERNS:
        raise ValueError('未知面部装饰图案')
    return next(row for row in catalogue()['patterns'] if row['id'] == pattern)
