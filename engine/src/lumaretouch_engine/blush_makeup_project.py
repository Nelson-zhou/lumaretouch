# SPDX-License-Identifier: GPL-3.0-or-later
"""Project/history adapter, original patterns are pinned independently of palette."""
from copy import deepcopy
from . import blush_makeup_state as S
from .blush_makeup_catalogue import CATALOGUE_SHA256,catalogue
KEY='blush_makeup_library'

def empty():return {'version':1,'catalogue_sha256':CATALOGUE_SHA256,'saved_colours':[]}

def check(value):
    if type(value) is not dict or set(value)!=set(empty()) or type(value['version']) is not int or value['version']!=1:
        raise ValueError('腮红收藏库字段或版本无效')
    if value['catalogue_sha256']!=CATALOGUE_SHA256:raise ValueError('工程使用不同腮红素材版本，需要显式迁移')
    catalogue()
    return {**empty(),'saved_colours':S.check_palette(value['saved_colours'])}

def capture(engine):return check(getattr(engine,'_blush_makeup_library',empty()))

def restore(engine,value):
    checked=check(value) # Validate before any mutation; no reinterpretation of corrupt/null data.
    engine._blush_makeup_library=deepcopy(checked)

def save(engine,project):project[KEY]=capture(engine)

def prepare(project):return check(project[KEY]) if KEY in project else empty()

def validate_records(value):
    """Validate dormant overrides and all undo/redo trees, not only current face."""
    if isinstance(value,dict):
        if KEY in value:check(value[KEY])
        if '_blush_makeup_library' in value:check(value['_blush_makeup_library'])
        for key in ('people_graph','_people_state'):
            if key in value:S.validate_graph(value[key])
        for child in value.values():validate_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_records(child)
