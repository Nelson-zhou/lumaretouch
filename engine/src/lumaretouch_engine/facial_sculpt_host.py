# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-source readback and explicit facial structure consent via people receipts.

No second graph, transaction, support bank or publication mechanism.
The original or derived effective source is read through the canonical source owner. The source
PNG is only a review page; normalized strokes, not pixels, survive in history.
"""
from copy import deepcopy
import base64
import hashlib
from . import facial_sculpt_state as S, people_state as P, facial_sculpt_support as V

ACTIONS = frozenset(('facial_sculpt_reference','facial_sculpt_review'))


def check_proof(proof):
    if type(proof) is not dict or set(proof) != {'source','face_ref','landmark_digest','preview_sha256','reference_request_id'}:
        raise ValueError('面部立体缺少原图显示与当前人物的精确审核证明')
    source = V.check_source(proof['source']); ref = P.check_ref(proof['face_ref'])
    if source['sha256'] != ref['asset_sha256']:
        raise ValueError('面部立体原图证明属于另一来源')
    P.digest(proof['landmark_digest']); P.digest(proof['preview_sha256']); P.token(proof['reference_request_id'])
    return deepcopy(proof)


def check_action(action, payload, target):
    if (action not in ACTIONS or type(target) is not dict or set(target) != {'scope','target_id','face_ref'}
            or target['scope'] != 'face' or type(payload) is not dict):
        raise ValueError('面部立体审核需要当前明确的单个人物')
    ref = P.check_ref(target['face_ref'])
    if ref['face_instance_id'] != target['target_id']: raise ValueError('面部立体人物引用与目标不匹配')
    if action == 'facial_sculpt_reference':
        if payload != {}: raise ValueError('面部立体原图请求不能指定外来来源')
    else:
        if set(payload) != {'region','reference_proof'}:
            raise ValueError('面部立体审核字段无效')
        proof = check_proof(payload['reference_proof']); V.check_region(payload['region'])
        if proof['face_ref'] != target['face_ref']:
            raise ValueError('面部立体审核证明属于另一人物')


def selected(engine, state, target):
    source = V.check_source(engine._people_source())
    if target['scope'] != 'face' or target != engine._people_targets.get(source['sha256']):
        raise ValueError('面部立体审核需要当前人物独立编辑范围')
    ref = P.check_ref(target['face_ref']); face = state['faces'].get(ref['face_instance_id'])
    if (face is None or P.face_ref(face) != ref or ref['asset_sha256'] != source['sha256']
            or engine._people_cursors.get(source['sha256']) != ref['face_instance_id'] or not face['enabled']
            or face['evidence']['status'] != 'verified' or face['evidence']['backend'] != 'mediapipe'
            or (face['evidence']['source_width'],face['evidence']['source_height']) != (source['width'],source['height'])):
        raise ValueError('面部立体需要当前有效来源中启用的真实分析人物')
    return source, ref


def binding(engine, state, target):
    return {**engine._people_binding(),'state_revision':state['revision'],
            'association_revision':state['association_revision'],'target':deepcopy(target)}


def support_status(engine, state, source, ref):
    """Admission only: the target renderer still measures marks and safe skin."""
    if ref is None: return False,'请先选择当前人物',None
    digest = None
    try:
        record, digest = V.resolve(state,engine._people_support,ref)
        if record['source'] != source: raise ValueError('面部立体审核来源尺寸已改变')
        face = state['faces'][ref['face_instance_id']]
        if not face['enabled']: raise ValueError('当前人物未启用')
        analysis = engine._people_analyses.get(source['sha256'],{}).get(ref['face_instance_id'])
        if analysis is None or analysis.get('face_skin') is None or analysis.get('excluded') is None:
            raise ValueError('目标人物缺少自己的真实皮肤与遮挡分析')
        from .people_render_runtime import verify_analysis
        verify_analysis(face,analysis,analysis['face_skin'].shape)
        from .skin_colour_support import check_analysis_fields
        if check_analysis_fields(analysis,analysis['face_skin'].shape) is None:
            raise ValueError('面部立体需要真实 face-skin 类别观察，不能借用合并皮肤蒙版')
        return True,None,digest
    except (ValueError,TypeError,KeyError,AttributeError) as error:
        return False,str(error),digest


def report(engine, state, source, selected_id):
    from . import people_algorithms as A, people_resolver as R
    from .facial_sculpt_native import available
    face = state['faces'].get(selected_id); recipe = S.neutral(); facts = {}; ref = None; landmark = None
    if face is not None and face['asset_sha256'] == source['sha256']:
        ref = P.face_ref(face); landmark = face['evidence']['landmark_digest']
        recipe = A.recipes(R.resolve(state,selected_id,A.defaults()))[S.OP]
        prepared = getattr(engine._vram,'people_prepared',None)
        records = [row for row in prepared.effects if row.stage == 'facial_sculpt' and row.face_ref == ref] if prepared else []
        if records: facts = dict(records[0].facts or {})
    supported, reason, digest = support_status(engine,state,source,ref)
    shown = getattr(engine,'_facial_sculpt_reference',None); target = engine._people_targets.get(source['sha256'])
    current = bool(shown and ref is not None and shown['proof']['source'] == source and shown['proof']['face_ref'] == ref
                   and shown['proof']['landmark_digest'] == landmark and shown['binding'] == binding(engine,state,target))
    alias_required = False; alias_reason = None
    try:
        from .facial_sculpt_project import require_unaliased
        from .virtual_copy_people import current_row
        require_unaliased(engine, current_row(engine), {source['sha256']})
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        alias_required = True; alias_reason = str(error)
    return {'alias_required': alias_required, 'alias_reason': alias_reason,
            'recipe': recipe, 'facts': facts, 'source': source, 'face_ref': ref, 'landmark_digest': landmark,
            'reviewed':digest is not None,'support_sha256':digest,
            'source_preview':deepcopy(shown['preview']) if current else None,
            'reference_proof':deepcopy(shown['proof']) if current else None,
            'native_available':available(),'support_available':supported,'support_reason':reason,
            'suspended':getattr(engine._vram,'people_suspended',None)}


def reference(engine, state, target, payload, *, request_id):
    check_action('facial_sculpt_reference',payload,target)
    source, ref = selected(engine,state,target); before = binding(engine,state,target)
    from .body_pose_commands import source_preview
    preview = source_preview(engine)
    if engine._people_source() != source or binding(engine,engine._people_owner().snapshot(),target) != before:
        raise ValueError('读取面部立体原图期间文档或人物改变')
    png = base64.b64decode(preview['base64'],validate=True)
    # A single full-frame PNG lives in doc_state, never duplicated in payload.
    if len(png) > 5*1024*1024: raise ValueError('面部立体原图参考超出回执大小预算')
    digest = hashlib.sha256(png).hexdigest()
    preview = {**preview,'sha256':digest}
    proof = check_proof({'source':source,'face_ref':ref,'landmark_digest':state['faces'][ref['face_instance_id']]['evidence']['landmark_digest'],
                         'preview_sha256':digest,'reference_request_id':request_id})
    engine._facial_sculpt_reference = {'proof':proof,'preview':preview,'binding':before}
    return {'kind':'facial_sculpt_reference','reference_proof':deepcopy(proof)}


def review_reference(engine, state, target, payload):
    """Validate the source page and paint without installing any support bank."""
    check_action('facial_sculpt_review',payload,target)
    source, ref = selected(engine,state,target); shown = getattr(engine,'_facial_sculpt_reference',None)
    proof = check_proof(payload['reference_proof'])
    if (not shown or shown['proof'] != proof or proof['source'] != source or proof['face_ref'] != ref
            or proof['landmark_digest'] != state['faces'][ref['face_instance_id']]['evidence']['landmark_digest']
            or shown['binding'] != binding(engine,state,target)):
        raise ValueError('面部立体原图显示、人物或文档已改变，请重新读取并审核')
    return source, ref, proof


def stage_review(engine, state, target, payload):
    source, ref, proof = review_reference(engine,state,target,payload)
    from .facial_sculpt_project import require_unaliased
    from .virtual_copy_people import current_row
    require_unaliased(engine,current_row(engine),{source['sha256']})
    candidate, assets = V.retain(state,engine._people_support,ref,payload['region'])
    from .people_support_assets import check_store
    check_store(assets)
    _, digest = V.resolve(candidate,assets,ref)
    engine._people_support = assets # Append-only. Existing publication owner commits the pointer.
    return candidate, {'kind':'facial_sculpt_review','reference_proof':proof,'support_sha256':digest}


def bound_receipt_images(records):
    """Keep one reference PNG, never 128 large nested doc_state copies.

    Released reads preserve terminal identity/outcome but cannot authorize a new
    review. Ordinary mutation receipts keep their outcomes and all other fields.
    """
    keep = None
    for request, row in reversed(records.items()):
        saved = row.get('result',row)
        report = ((saved.get('doc_state') or {}).get('people') or {}).get('facial_sculpt')
        if (saved.get('action') == 'facial_sculpt_reference' and saved.get('success') is True
                and type(report) is dict and report.get('source_preview') is not None):
            keep = request
            break
    for request, row in records.items():
        if request == keep: continue
        saved = row.get('result',row)
        report = ((saved.get('doc_state') or {}).get('people') or {}).get('facial_sculpt')
        if type(report) is not dict or report.get('source_preview') is None: continue
        if saved.get('action') == 'facial_sculpt_reference' and saved.get('success') is True:
            # A successful read remains a successful read, but its display page
            # expired. No mutation outcome or request digest is rewritten.
            saved.pop('payload',None); saved.pop('doc_state',None)
            saved['payload_released'] = True
        else:
            report['source_preview'] = None; report['reference_proof'] = None
