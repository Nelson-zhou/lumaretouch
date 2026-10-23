# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable original analytic materials; hash pinned so projects are reproducible."""
import hashlib
import json
from pathlib import Path
from copy import deepcopy
from .blush_makeup_state import PATTERNS
CATALOGUE_SHA256 = "e434170ee59d36942c27c82501ae1411af7f077f2520ffda5470770d741daaba"

def catalogue():
    raw=Path(__file__).with_name('blush_makeup_patterns.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOGUE_SHA256:
        raise ValueError('腮红素材目录损坏或版本改变，未替换已保存效果')
    value=json.loads(raw)
    if tuple(p['id'] for p in value['patterns'])!=PATTERNS:raise ValueError('腮红素材身份不匹配')
    return deepcopy(value)

def material(pattern):
    return next(p for p in catalogue()['patterns'] if p['id']==pattern)
