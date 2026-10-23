# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical PeopleGraphOwner adapter; never a parallel graph or history."""
from . import iris_makeup_state as S, iris_makeup_support as V
from .iris_makeup_layer import prepare_record

def prepare(state,assets,face_ref,analysis,source,recipe):
    if not S.active(recipe):return []
    if analysis.get('face_ref')!=face_ref:raise ValueError('美瞳分析人物已改变')
    reviewed,_=V.resolve(state,assets,face_ref)
    face=state['faces'][face_ref['face_instance_id']]
    from .people_render_runtime import verify_analysis
    lm=verify_analysis(face,analysis,source.shape[:2])
    record=prepare_record(face_ref,lm,recipe,source,excluded=analysis.get('excluded'),backend=face['evidence']['backend'],reviewed=reviewed)
    return [] if record is None else [record]
