"""Reachable graph-owned eyeliner read/review commands; no second history owner."""
from copy import deepcopy
from pathlib import Path
from . import people_state as P, people_algorithms as A, eyeliner_state as S
from . import eyeliner_support as V

def selected(engine,state,target):
    source=engine._people_source()
    if target['scope']!='face' or target!=engine._people_targets.get(source['sha256']): raise ValueError('眼线审核只属于当前明确选中的人物')
    ref=P.check_ref(target['face_ref']);face=state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face)!=ref or ref['asset_sha256']!=source['sha256'] or not face['enabled'] or face['evidence']['status']!='verified': raise ValueError('需要当前源照片中启用且完成真实分析的人物')
    return source,ref

def reference(engine,state,target,payload):
    if payload!={}: raise ValueError('眼线原图请求字段无效')
    source,ref=selected(engine,state,target)
    from .body_pose_commands import source_preview
    preview=source_preview(engine)
    if engine._people_source()!=source: raise ValueError('原图准备期间照片改变')
    engine._eyeliner_reference={'source':deepcopy(source),'face_ref':ref,'preview':preview}

def stage_review(engine,state,target,payload):
    if type(payload) is not dict or set(payload)!={'eyes'}: raise ValueError('眼线审核字段无效')
    source,ref=selected(engine,state,target);shown=getattr(engine,'_eyeliner_reference',None)
    if not shown or shown['source']!=source or shown['face_ref']!=ref: raise ValueError('请先读取当前人物的原图参考，再保存审核')
    candidate,assets=V.retain(state,engine._people_support,ref,payload['eyes'])
    from .people_support_assets import check_store
    check_store(assets)
    # Append-only bytes are safe to retain on a later rejected graph mutation;
    # no face pointer/recipe is committed until the normal transaction publishes.
    engine._people_support=assets
    return candidate

def report(engine,state,source,selected_id):
    from .people_resolver import resolve
    face=state['faces'].get(selected_id)
    if face is None:return None
    ref=P.face_ref(face);resolved=resolve(state,selected_id,A.defaults())
    recipe=A.recipes(resolved)[S.OPERATION]
    descriptor=face['local_assets'].get(V.KIND);shown=getattr(engine,'_eyeliner_reference',None)
    prepared=getattr(engine._vram,'people_prepared',None)
    records=[r for r in prepared.effects if r.stage=='eyeliner' and r.face_ref==ref] if prepared else []
    native=(Path(__file__).resolve().parent/'bin/liblrt_eyeliner.so').is_file()
    from .eyeliner_project import capture
    return {'library':capture(engine),'recipe':recipe,'source':deepcopy(source),'face_ref':ref,'reviewed':descriptor is not None,
        'native_available':native,'reason':('no_measurable_change' if records and not any(int((r.facts or {}).get('changed_pixels',0)) for r in records) else None),'changed_pixels':sum(int((r.facts or {}).get('changed_pixels',0)) for r in records),
        'suspended':getattr(engine._vram,'people_suspended',None),
        'source_preview':shown['preview'] if shown and shown['source']==source and shown['face_ref']==ref else None}


def palette_action(engine,command):
    from . import eyeliner_project as LIB
    from .eyeliner_adapters import stage_palette
    old=LIB.capture(engine);candidate=stage_palette(engine,command)
    if old==candidate:return
    try:
        LIB.restore(engine,candidate)
        engine._fence_current_document()
    except Exception:
        LIB.restore(engine,old)
        raise
