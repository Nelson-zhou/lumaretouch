# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-photo reference/readback/review through existing people receipt owner.

No new transaction owner. Parent must whitelist both actions, bind/echo exact
requests and route read vs mutation correctly. Confirmed support is append-only.
"""
from copy import deepcopy
from . import eye_makeup_enhance_state as S, eye_makeup_enhance_support as V, people_state as P
ACTIONS=frozenset(('eye_makeup_enhance_reference','eye_makeup_enhance_review'))
READS=frozenset(('eye_makeup_enhance_reference',))


def check_proof(value):
    if type(value) is not dict or set(value)!={'source','face_ref','landmark_digest','preview_sha256','reference_request_id'}:
        raise ValueError('眼妆审核需要准确源图显示证明')
    source=V.check_source(value['source']); ref=P.check_ref(value['face_ref'])
    if source['sha256']!=ref['asset_sha256']: raise ValueError('眼妆显示证明属于另一来源')
    P.digest(value['landmark_digest']);P.digest(value['preview_sha256']);P.token(value['reference_request_id'])
    return deepcopy(value)


def check_action(action,payload,target):
    if (action not in ACTIONS or type(target) is not dict or set(target)!={'scope','target_id','face_ref'}
            or target['scope']!='face' or type(payload) is not dict):
        raise ValueError('眼妆审核仅支持当前明确的单个人物')
    ref=P.check_ref(target['face_ref'])
    if ref['face_instance_id']!=target['target_id']: raise ValueError('眼妆审核目标不匹配')
    if action=='eye_makeup_enhance_reference':
        if payload!={}: raise ValueError('眼妆参考请求不能携带外来图像')
    else:
        if set(payload)!={'eyes','reference_proof'}: raise ValueError('眼妆审核字段无效')
        proof=check_proof(payload['reference_proof']);V.check_eyes(payload['eyes'])
        if proof['face_ref']!=ref: raise ValueError('眼妆审核证明属于其他人物')


def selected(engine,state,target):
    source=V.check_source(engine._people_source())
    if target['scope']!='face' or target!=engine._people_targets.get(source['sha256']):
        raise ValueError('眼妆审核需要当前人物独立编辑范围')
    ref=P.check_ref(target['face_ref']);face=state['faces'].get(ref['face_instance_id'])
    if (face is None or P.face_ref(face)!=ref or ref['asset_sha256']!=source['sha256']
            or engine._people_cursors.get(source['sha256'])!=ref['face_instance_id'] or not face['enabled']
            or face['evidence']['status']!='verified' or face['evidence']['backend']!='mediapipe'
            or (face['evidence']['source_width'],face['evidence']['source_height'])!=(source['width'],source['height'])):
        raise ValueError('眼妆审核需要当前来源中启用且真实分析的人物')
    return source,ref


def binding(engine,state,target):
    return {**engine._people_binding(),'state_revision':state['revision'],
            'association_revision':state['association_revision'],'target':deepcopy(target)}


def reference(engine,state,target,payload,*,request_id):
    check_action('eye_makeup_enhance_reference',payload,target)
    source,ref=selected(engine,state,target);before=binding(engine,state,target)
    from .eye_makeup_enhance_reference import acquire
    preview=acquire(engine,source,ref)
    if engine._people_source()!=source or binding(engine,engine._people_owner().snapshot(),target)!=before:
        raise ValueError('眼妆参考读取期间文档或人物改变')
    proof=check_proof({'source':source,'face_ref':ref,'landmark_digest':state['faces'][ref['face_instance_id']]['evidence']['landmark_digest'],
        'preview_sha256':preview['sha256'],'reference_request_id':request_id})
    engine._eye_makeup_enhance_reference={'proof':proof,'preview':preview,'binding':before}
    return {'kind':'eye_makeup_enhance_reference','reference_proof':deepcopy(proof)}


def stage_review(engine,state,target,payload):
    check_action('eye_makeup_enhance_review',payload,target)
    source,ref=selected(engine,state,target);proof=check_proof(payload['reference_proof'])
    shown=getattr(engine,'_eye_makeup_enhance_reference',None)
    if (not shown or shown['proof']!=proof or proof['source']!=source or proof['face_ref']!=ref
            or proof['landmark_digest']!=state['faces'][ref['face_instance_id']]['evidence']['landmark_digest']
            or shown['binding']!=binding(engine,state,target)):
        raise ValueError('眼妆原图显示、文档、人物或分析已经改变，请重新读取并审核')
    from .eye_makeup_enhance_project import require_unaliased
    from .virtual_copy_people import current_row
    require_unaliased(engine,current_row(engine),{source['sha256']})
    candidate,bank=V.retain(state,engine._people_support,ref,payload['eyes'])
    from .people_support_assets import check_store
    check_store(bank);_,digest=V.resolve(candidate,bank,ref)
    engine._people_support=bank  # Immutable bytes only; host publishes the graph pointer atomically.
    return candidate,{'kind':'eye_makeup_enhance_review','reference_proof':proof,'support_sha256':digest}


def report(engine,state,source,selected_id):
    from . import people_algorithms as A, people_resolver as R
    from .eye_makeup_enhance_native import available
    face=state['faces'].get(selected_id);ref=None;landmark=None;recipe=S.neutral();facts={}
    digest=None;reason=None;sides={};supported=False
    if face is not None and face['asset_sha256']==source['sha256']:
        ref=P.face_ref(face);landmark=face['evidence']['landmark_digest']
        resolved=R.resolve(state,selected_id,A.defaults())
        if not any(c['operation_id']==S.OP for c in resolved['conflicts']):
            recipe=R.materialize({**resolved,'conflicts':[]},S.OP,S.neutral(),S.check)
        else: reason='眼妆参数有继承冲突，请先解决'
        prepared=getattr(engine._vram,'people_prepared',None)
        records=[row for row in prepared.effects if row.stage=='eye_makeup_enhance' and row.face_ref==ref] if prepared else []
        if records: facts=dict(records[0].facts or {})
    try:
        if ref is None: raise ValueError('请选择当前真实人物')
        record,digest=V.resolve(state,engine._people_support,ref)
        if record['source']!=source: raise ValueError('眼妆审核来源尺寸改变')
        if not face['enabled']: raise ValueError('人物未启用')
        analysis=engine._people_analyses.get(source['sha256'],{}).get(ref['face_instance_id'])
        if analysis is None or analysis.get('face_skin') is None or analysis.get('excluded') is None:
            raise ValueError('眼妆缺少当前人物真实皮肤与遮挡分析')
        from .people_render_runtime import verify_analysis
        from .skin_colour_support import check_analysis_fields
        verify_analysis(face,analysis,analysis['face_skin'].shape)
        if check_analysis_fields(analysis,analysis['face_skin'].shape) is None: raise ValueError('眼妆缺少真实皮肤观察')
        sides={side:{'reviewed':True,'reference_reviewed':eye['reference_confirmed']} for side,eye in record['row']['eyes'].items()}
        supported=True
    except (ValueError,TypeError,KeyError,AttributeError) as error: reason=str(error)
    target=engine._people_targets.get(source['sha256']);shown=getattr(engine,'_eye_makeup_enhance_reference',None)
    current=bool(shown and ref is not None and shown['proof']['source']==source and shown['proof']['face_ref']==ref
        and shown['proof']['landmark_digest']==landmark and shown['binding']==binding(engine,state,target))
    return {'recipe':recipe,'facts':facts,'source':source,'face_ref':ref,'landmark_digest':landmark,
        'reviewed':digest is not None,'support_sha256':digest,'sides':sides,
        'source_preview':deepcopy(shown['preview']) if current else None,
        'reference_proof':deepcopy(shown['proof']) if current else None,'native_available':available(),
        'support_available':supported,'support_reason':reason,'suspended':getattr(engine._vram,'people_suspended',None)}


def bound_receipt_images(records):
    keep=None
    for request,row in reversed(records.items()):
        saved=row.get('result',row);report=((saved.get('doc_state') or {}).get('people') or {}).get('eye_makeup_enhance')
        if saved.get('action')=='eye_makeup_enhance_reference' and saved.get('success') is True and type(report) is dict and report.get('source_preview') is not None:
            keep=request;break
    for request,row in records.items():
        if request==keep: continue
        saved=row.get('result',row);report=((saved.get('doc_state') or {}).get('people') or {}).get('eye_makeup_enhance')
        if type(report) is not dict or report.get('source_preview') is None: continue
        if saved.get('action')=='eye_makeup_enhance_reference' and saved.get('success') is True:
            saved.pop('payload',None);saved.pop('doc_state',None);saved['payload_released']=True
        else:
            report['source_preview']=None;report['reference_proof']=None
