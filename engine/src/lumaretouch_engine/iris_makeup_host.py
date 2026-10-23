# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
from . import iris_makeup_state as S, people_state as P

def report(engine,state,source,selected_id):
    from . import people_algorithms as A,people_resolver as R
    face=state['faces'].get(selected_id);recipe=S.neutral();facts={}
    if face is not None and face['asset_sha256']==source['sha256']:
        recipe=A.recipes(R.resolve(state,selected_id,A.defaults()))[S.OP]
        prepared=getattr(engine._vram,'people_prepared',None)
        records=[r for r in prepared.effects if r.stage=='iris_makeup' and r.face_ref==P.face_ref(face)] if prepared else []
        if records:facts=dict(records[0].facts or {})
    from .iris_makeup_support import KIND
    shown=getattr(engine,'_iris_makeup_reference',None);ref=P.face_ref(face) if face is not None else None
    return {'recipe':recipe,'facts':facts,'source':source,'face_ref':ref,
            'reviewed':bool(face and KIND in face['local_assets']),
            'source_preview':shown['preview'] if shown and shown['source']==source and shown['face_ref']==ref else None,
            'native_available':(Path(__file__).resolve().parent/'bin/liblrt_iris_makeup.so').is_file(),
            'suspended':getattr(engine._vram,'people_suspended',None)}

def selected(engine,state,target):
    source=engine._people_source()
    if target['scope']!='face' or target!=engine._people_targets.get(source['sha256']):raise ValueError('美瞳审核需要当前人物独立编辑范围')
    ref=P.check_ref(target['face_ref']);face=state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face)!=ref or ref['asset_sha256']!=source['sha256'] or not face['enabled'] or face['evidence']['status']!='verified':raise ValueError('需要当前源照片中启用的真实分析人物')
    return source,ref

def reference(engine,state,target,payload):
    from copy import deepcopy
    if payload!={}:raise ValueError('美瞳原图参考请求字段无效')
    source,ref=selected(engine,state,target)
    from .iris_makeup_reference import acquire
    preview=acquire(engine,source,ref)
    if engine._people_source()!=source:raise ValueError('读取原图期间照片改变')
    engine._iris_makeup_reference={'source':deepcopy(source),'face_ref':ref,'preview':preview}

def stage_review(engine,state,target,payload):
    from . import iris_makeup_support as V
    from .people_support_assets import check_store
    if type(payload) is not dict or set(payload)!={'eyes'}:raise ValueError('美瞳审核字段无效')
    source,ref=selected(engine,state,target);shown=getattr(engine,'_iris_makeup_reference',None)
    if not shown or shown['source']!=source or shown['face_ref']!=ref:raise ValueError('请先读取当前人物的原图参考，再保存审核')
    candidate,assets=V.retain(state,engine._people_support,ref,payload['eyes'])
    check_store(assets);engine._people_support=assets # Append-only; no graph publication yet.
    return candidate
