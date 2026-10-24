"""Reachable document-bound people edits, existing history and batch receipts."""
from collections import OrderedDict
from copy import deepcopy
import uuid
import hashlib
import json
from . import people_state as S,people_algorithms as A,people_edit as EDIT
from .people_command import validate_envelope
from .people_graph_owner import affected_assets


FACE_STYLE_READS = frozenset(('face_style_catalog','face_style_preview','face_style_image'))
FACE_STYLE_ACTIONS = FACE_STYLE_READS | {'face_style_confirm'}
EYE_BAG_READS = frozenset(('eye_bag_source_image','eye_bag_reference','eye_bag_preview','eye_bag_image'))
EYE_BAG_ACTIONS = EYE_BAG_READS | {'eye_bag_confirm'}
DECORATION_ALIAS_READS = frozenset(('face_decoration_alias_preview','face_decoration_alias_image'))
DECORATION_ALIAS_ACTIONS = DECORATION_ALIAS_READS | {'face_decoration_alias_confirm'}
DECORATION_SUPPORT_ALIAS_READS = frozenset(('face_decoration_support_alias_preview','face_decoration_support_alias_image'))
DECORATION_SUPPORT_ALIAS_ACTIONS = DECORATION_SUPPORT_ALIAS_READS | {'face_decoration_support_alias_confirm'}
DECORATION_READS = frozenset(('face_decoration_reference',)) | DECORATION_ALIAS_READS | DECORATION_SUPPORT_ALIAS_READS
DECORATION_ACTIONS = DECORATION_READS | {'face_decoration_review','face_decoration_alias_confirm','face_decoration_support_alias_confirm'}


def face_style_read_only(raw):
    """Exact read route only; existing recovery/import/source guards run first."""
    return _review_read_only(raw,FACE_STYLE_READS)


def eye_bag_read_only(raw):
    """Independent eye-bag reference/review pages, never graph publication."""
    return _review_read_only(raw,EYE_BAG_READS)


def face_decoration_read_only(raw):
    return _review_read_only(raw,DECORATION_READS)


def _review_read_only(raw,actions):
    if (type(raw) is not dict or raw.get('cmd') != 'people'
            or type(raw.get('action')) is not str or raw['action'] not in actions):
        return False
    if set(raw) != {'cmd','document_id','document_epoch','document_revision','state_revision','association_revision','request_id','target','action','payload'}:
        return False
    try:
        if raw['action'] in DECORATION_READS:
            from .face_decoration_host import check_action
        elif raw['action'] in EYE_BAG_READS:
            from .eye_bag_preserve_host import check_action
        else:
            from .face_style_review import check_action
        for key in ('document_id','document_epoch','request_id'): S.token(raw[key])
        for key in ('document_revision','state_revision','association_revision'): S.revision(raw[key])
        check_action(raw['action'],raw['payload'],raw['target'])
        return True
    except (ValueError,TypeError,KeyError):
        return False


def checked(engine,p):
    why=engine._guard_editable('people')
    if why:raise ValueError(why)
    style_action=p.get('action') in FACE_STYLE_ACTIONS
    eye_bag_action=p.get('action') in EYE_BAG_ACTIONS
    decoration_action=p.get('action') in DECORATION_ACTIONS
    if style_action or eye_bag_action or decoration_action:
        from .people_preset_plan import require_active_owner
        owner=require_active_owner(engine)
    else:
        engine._people_bind();owner=engine._people_owner()
    binding=engine._people_binding();state=owner.snapshot()
    target=validate_envelope(p,state,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')})
    asset=binding['asset_sha256']
    if (target['scope']=='face' and target['face_ref']['asset_sha256']!=asset) or (target['scope']=='all_people' and target['target_id']!=asset):
        raise ValueError('People command targets another source asset')
    if style_action or eye_bag_action or decoration_action:
        if decoration_action:
            from .face_decoration_host import check_action
        elif eye_bag_action:
            from .eye_bag_preserve_host import check_action
        else:
            from .face_style_review import check_action
        check_action(p['action'],p.get('payload'),target)
        if (target['scope']!='face' or not state['faces'][target['target_id']]['enabled']
                or engine._people_targets.get(asset)!=target
                or engine._people_cursors.get(asset)!=target['target_id']):
            raise ValueError('Portrait image review requires the currently selected enabled source face')
    return state,binding,target


def select(engine,state,asset,target):
    from dataclasses import replace
    key=target['target_id'];face=state['faces'][key]
    engine._people_cursors[asset]=key;engine._people_targets[asset]=deepcopy(target)
    engine._face_box=tuple(face['box']);engine._face_explicit=True
    analysis=engine._people_analyses.get(asset,{}).get(key)
    if analysis is not None and engine._precompute is not None:
        engine._precompute=replace(engine._precompute,landmarks=analysis['landmarks'],face_box=tuple(face['box']))
    engine._people_analysis_key=None;engine._people_mirror()


def publish(engine,before,candidate,request_id,*,shared=False,before_publish=None):
    assets=affected_assets(before,candidate);assets.add(engine._people_source()['sha256'])
    if shared:
        if before_publish is not None:raise ValueError('Reviewed local publication cannot become a shared edit')
        from .people_batch_ledger import commit
        result=commit(engine._batch_controller(),engine,before,candidate,request_id=request_id)
        return result if result else (None,None)
    engine._people_prepare_graph(candidate,assets)
    try:
        if before_publish is not None:before_publish()
        return None,engine._people_publish_graph(candidate,assets)
    finally:
        if before_publish is not None:engine._people_staged=None


def analyse(engine,state,face_ref):
    from types import SimpleNamespace
    from . import face as F,people_binding as B,people_associations as G,people_retained_analysis as RA
    from .nose_shape_runtime import exclusion
    from .facial_wrinkle_runtime import skin_support
    from .skin_colour_support import analysis_fields as skin_colour_fields
    from .body_skin_semantics import analysis_fields as body_skin_fields, check_analysis_fields as check_body_skin_fields
    import numpy as np
    face=state['faces'][face_ref['face_instance_id']];source=engine._people_source()
    from .creative_derived_source import analysis_rgb, stamp_precompute, verify_precompute
    rgb=analysis_rgb(engine)
    verify_precompute(engine,engine._precompute)
    if face['local_assets']:raise ValueError('Reanalysis cannot silently rebind existing source-owned recovery; retain it and review explicitly')
    with F.MediaPipeFace() as backend:
        points,_=F.detect_region(backend,rgb,face['box'])
        pc=SimpleNamespace(backend='mediapipe',detector_model_sha256=backend.detector_model_sha256,semantic_model_sha256=backend.semantic_model_sha256)
        evidence=B.evidence(pc,points,(source['width'],source['height']))
        original=engine._precompute
        if original is None:
            original=F.FacePrecompute(landmarks=points,masks=backend.semantic_masks(rgb),backend='mediapipe',
                t_detect_ms=0.,t_masks_ms=0.,face_box=tuple(face['box']),all_landmarks=[points],manual=(0,),
                detector_model_sha256=backend.detector_model_sha256,semantic_model_sha256=backend.semantic_model_sha256)
            engine._precompute=original;engine._precompute_backend='mediapipe'
            stamp_precompute(engine,original,rgb)
        if original.semantic_model_sha256!=evidence['semantic_model_sha256']:
            raise ValueError('Region analysis lacks matching full-source semantic evidence')
    out=G.reanalyse(state,source['sha256'],{face_ref['face_instance_id']:evidence},expected_revision=state['revision'],user_confirmed=True)
    ref=S.face_ref(out['faces'][face_ref['face_instance_id']]);points=np.array(points,dtype='<f4',copy=True);points.setflags(write=False)
    row={'face_ref':ref,'evidence':evidence,'landmarks':points,'excluded':exclusion(original),'skin':skin_support(original),
         **skin_colour_fields(original, source['sha256'], (source['width'], source['height'])),
         **body_skin_fields(original, source['sha256'], (source['width'], source['height']))}
    check_body_skin_fields(row)
    engine._people_landmarks=RA.retain(engine._people_landmarks,{ref['face_instance_id']:row})
    engine._people_analyses.setdefault(source['sha256'],{})[ref['face_instance_id']]=row
    return out,ref


def apply(engine,raw,emit):
    if type(raw) is not dict or raw.get('cmd')!='people':raise ValueError('Invalid people command')
    p={k:v for k,v in raw.items() if k!='cmd'}
    if set(p)!={'document_id','document_epoch','document_revision','state_revision','association_revision','request_id','target','action','payload'}:raise ValueError('Invalid people command fields')
    records=engine.__dict__.setdefault('_people_receipts',OrderedDict());request=S.token(p.get('request_id'))
    digest=hashlib.sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if request in records:
        if records[request].get('digest')!=digest:raise ValueError('People request identity was reused with different content')
        return # Finish emits the original correlated result, never applies twice.
    records[request]={'success':False,'digest':digest};state,binding,target=checked(engine,p);asset=binding['asset_sha256']
    records[request]['before_fence']=engine._people_owner().fence
    action=p.get('action');payload=p.get('payload');created=None;batch_id=None
    if action in DECORATION_SUPPORT_ALIAS_READS:
        from . import face_decoration_support_alias_review as support_aliases
        method=support_aliases.preview if action=='face_decoration_support_alias_preview' else support_aliases.image
        records[request]['payload']=method(engine,state,target,payload)
        frame=None
    elif action in DECORATION_ALIAS_READS:
        from . import face_decoration_alias_review as aliases
        method=aliases.preview if action=='face_decoration_alias_preview' else aliases.image
        records[request]['payload']=method(engine,state,target,payload)
        frame=None
    elif action in FACE_STYLE_READS:
        from . import face_style_review as style_review
        method={'face_style_catalog':style_review.catalogue,'face_style_preview':style_review.preview,'face_style_image':style_review.image}[action]
        records[request]['payload']=method(engine,state,target,payload)
        frame=None
    elif action in EYE_BAG_READS:
        from . import eye_bag_preserve_host as eye_bag_review
        method={'eye_bag_source_image':eye_bag_review.source_image,'eye_bag_reference':eye_bag_review.reference,'eye_bag_preview':eye_bag_review.preview,
                'eye_bag_image':eye_bag_review.image}[action]
        from . import eye_bag_review_jobs as jobs
        try:records[request]['payload']=jobs.run(engine,request,method,state,target,payload)
        except jobs.Cancelled:
            records[request]['eye_bag_cancelled']=True
            raise
        frame=None
    elif action in ('skin_body_reference','skin_body_preview','skin_finish_body_reference','skin_finish_body_preview','body_skin_evenness_reference','body_skin_evenness_preview','collarbone_reference','collarbone_preview','body_face_match_reference','body_face_match_preview'):
        from . import skin_colour_body_host as skin_body
        method=skin_body.reference if action.endswith('_reference') else skin_body.preview
        options={'family':'skin_finish'} if action.startswith('skin_finish_body_') else {}
        if action.startswith('collarbone_'):options={'family':'collarbone','operation_id':'lnx.collarbone.v1'}
        if action.startswith('body_skin_evenness_'):options={'family':'body_skin_evenness','operation_id':'lnx.body_skin_evenness.v1'}
        if action.startswith('body_face_match_'):options={'family':'body_face_match','operation_id':'lnx.body_face_match.v1'}
        records[request]['payload']=method(engine,state,target,payload,**options)
        skin_body.bound_receipt_payloads(records)
        frame=None
    elif action=='iris_reference':
        from .iris_makeup_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='eyelash_palette':
        from .eyelash_host import palette_action
        palette_action(engine,p)
        frame=None
    elif action=='eyelash_reference':
        from .eyelash_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='eyeliner_palette':
        from .eyeliner_host import palette_action
        palette_action(engine,p)
        frame=None
    elif action=='eyeliner_reference':
        from .eyeliner_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='brow_makeup_palette':
        from .brow_makeup_host import palette_action
        palette_action(engine,p)
        frame=None
    elif action=='brow_makeup_reference':
        from .brow_makeup_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='lipstick_palette':
        from .lipstick_host import palette_action
        palette_action(engine,p)
        frame=None
    elif action=='lipstick_reference':
        from .lipstick_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='blush_palette':
        from .blush_makeup_host import palette_action
        palette_action(engine,p)
        frame=None
    elif action=='face_decoration_reference':
        from .face_decoration_host import reference
        records[request]['payload']=reference(engine,state,target,payload,request_id=request)
        frame=None
    elif action=='blush_reference':
        from .blush_makeup_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action=='eye_light_reference':
        from .eye_light_host import reference
        reference(engine,state,target,payload)
        frame=None
    elif action in ('select','target'):
        if payload!={} or set(p)!={'document_id','document_epoch','document_revision','state_revision','association_revision','request_id','target','action','payload'}:raise ValueError('Invalid editing cursor command')
        # Cursor state can change before document fencing or synchronization fails.
        if action=='select':
            if target['scope']!='face':raise ValueError('Selection needs an exact retained face')
            records[request]['side_effects_started']=True
            select(engine,state,asset,target)
        else:
            records[request]['side_effects_started']=True
            engine._people_targets[asset]=deepcopy(target)
        engine._fence_current_document();engine._people_shared_mutation=True
        # Cursor/scope changes never require image rendering and must remain
        # reachable while a requested face is suspended for correction.
        engine._people_sync();frame=None
    else:
        before_publish=None
        if action=='face_decoration_support_alias_confirm':
            from . import face_decoration_support_alias_review as decoration_support_alias
            candidate,records[request]['payload']=decoration_support_alias.confirm(engine,state,target,payload)
        elif action=='face_decoration_alias_confirm':
            from . import face_decoration_alias_review as decoration_alias
            candidate,records[request]['payload']=decoration_alias.confirm(engine,state,target,payload)
        elif action=='face_style_confirm':
            from . import face_style_review as style_review
            candidate,records[request]['payload']=style_review.confirm(engine,state,target,payload)
            before_publish=lambda:style_review.verify_before_publish(engine,state,target,payload,candidate,records[request]['payload'])
        elif action=='eye_bag_confirm':
            from . import eye_bag_preserve_host as eye_bag_review
            candidate,records[request]['payload']=eye_bag_review.confirm(engine,state,target,payload)
            def before_publish():
                eye_bag_review.verify_before_publish(engine,state,target,payload,candidate,records[request]['payload'])
                records[request]['side_effects_started']=True
        elif action in ('skin_body_confirm','skin_body_detach','skin_finish_body_confirm','skin_finish_body_detach','body_skin_evenness_confirm','body_skin_evenness_detach','collarbone_confirm','collarbone_detach','body_face_match_confirm','body_face_match_detach'):
            from . import skin_colour_body_host as skin_body
            method=skin_body.confirm if action.endswith('_confirm') else skin_body.detach
            options={'mark_started':lambda:records[request].update(side_effects_started=True)} if action.endswith('_confirm') else {}
            if action.startswith('skin_finish_body_'):options['family']='skin_finish'
            if action.startswith('collarbone_'):options.update(family='collarbone',operation_id='lnx.collarbone.v1')
            if action.startswith('body_skin_evenness_'):options.update(family='body_skin_evenness',operation_id='lnx.body_skin_evenness.v1')
            if action.startswith('body_face_match_'):options.update(family='body_face_match',operation_id='lnx.body_face_match.v1')
            candidate,records[request]['payload']=method(engine,state,target,payload,**options)
        elif action=='analyse_face':
            if payload!={} or target['scope']!='face':raise ValueError('Region analysis needs an explicit face')
            records[request]['side_effects_started']=True
            candidate,ref=analyse(engine,state,target['face_ref'])
            target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
        elif action=='iris_review':
            from .iris_makeup_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='eyeliner_review':
            from .eyeliner_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='eyelash_review':
            from .eyelash_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='brow_makeup_review':
            from .brow_makeup_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='lipstick_review':
            from .lipstick_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='face_decoration_review':
            from .face_decoration_host import stage_review
            candidate,records[request]['payload']=stage_review(engine,state,target,payload)
        elif action=='blush_review':
            from .blush_makeup_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='eye_light_review':
            from .eye_light_host import stage_review
            candidate=stage_review(engine,state,target,payload)
        elif action=='resolve_legacy':
            from .people_legacy_review import resolve
            if type(payload) is not dict or set(payload)!={'archive_id','mode'}:raise ValueError('Invalid legacy review decision')
            candidate=resolve(state,payload['archive_id'],target,payload['mode'])
        else:
            source=engine._people_source()
            result=EDIT.stage(p,state,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},asset_sha256=asset,source_dimensions=(source['width'],source['height']))
            candidate=result['state'];created=result['created_id']
        shared=action in ('link','group','create_person') or target['scope'] in ('person','group')
        if action=='resolve_legacy' and any(x['asset_sha256']==asset and x['status']=='unresolved' for x in candidate['unresolved_legacy']):
            frame=engine._people_publish_pending_review(candidate)
        else:
            try:
                if action=='face_decoration_support_alias_confirm':
                    batch_id,frame=decoration_support_alias.publish(engine,state,target,payload,candidate,records[request]['payload'],request_id=request,mark_started=lambda:records[request].update(side_effects_started=True))
                    # Retain the known ledger identity before status/readback or
                    # frame emission can fail. Identity is not success proof.
                    records[request]['batch_id']=batch_id
                elif action=='face_decoration_alias_confirm':
                    batch_id,frame=decoration_alias.publish(engine,state,target,payload,candidate,records[request]['payload'],request_id=request,mark_started=lambda:records[request].update(side_effects_started=True))
                elif action=='face_style_confirm' and records[request]['payload'].get('alias_members') is not None:
                    # The frozen complete alias set belongs to the existing
                    # protected batch ledger, never a hidden local face write.
                    batch_id,frame=style_review.publish_alias(engine,state,target,payload,candidate,records[request]['payload'],request_id=request)
                elif action=='eye_bag_confirm' and records[request]['payload'].get('alias_members') is not None:
                    batch_id,frame=eye_bag_review.publish_alias(engine,state,target,payload,candidate,records[request]['payload'],request_id=request)
                else:batch_id,frame=publish(engine,state,candidate,request,shared=shared,before_publish=before_publish)
            except Exception as publish_error:
                if action=='face_decoration_support_alias_confirm':
                    for key in ('side_effects_started','rolled_back','requires_reload'):
                        if hasattr(publish_error,key):records[request][key]=bool(getattr(publish_error,key))
                    for key in ('batch_id','face_decoration_support_alias_review','alias_members'):
                        if hasattr(publish_error,key):records[request][key]=deepcopy(getattr(publish_error,key))
                # A rejected preparation may leave only append-only unused
                # support bytes. With an unchanged graph fence no pixels/recipe
                # were published; do not manufacture an uncertain edit lock.
                if action in ('skin_body_confirm','skin_finish_body_confirm','body_skin_evenness_confirm','collarbone_confirm','body_face_match_confirm') and engine._people_owner().fence==records[request]['before_fence']:
                    records[request]['side_effects_started']=False
                raise
        if action=='face_decoration_support_alias_confirm':
            decoration_support_alias.verify_after_publish(engine,candidate,records[request]['payload'])
            from .face_decoration_support_alias_history import status_summary
            records[request]['face_decoration_support_alias_review']=status_summary(engine._batch_controller().ledger[batch_id])
            records[request]['alias_members']=deepcopy(records[request]['payload']['alias_members'])
        if action=='face_decoration_alias_confirm':decoration_alias.verify_after_publish(engine,candidate,records[request]['payload'])
        if action=='face_style_confirm':style_review.verify_after_publish(engine,candidate,records[request]['payload'])
        if action=='eye_bag_confirm':eye_bag_review.verify_after_publish(engine,candidate,records[request]['payload'])
        if action=='analyse_face':select(engine,engine._people_owner().snapshot(),asset,target)
        if frame is not None:frame['doc_state']=engine.doc_state()
    if frame is not None:emit(frame)
    records[request].update(success=True,frame_emitted=frame is not None,created_id=created,batch_id=batch_id)
    while len(records)>128:records.popitem(last=False)


def finish(engine,p,error,emit):
    if type(p.get('request_id')) is not str:return
    records=engine.__dict__.setdefault('_people_receipts',OrderedDict());old=records.get(p['request_id'],{})
    style_action=p.get('action') in FACE_STYLE_ACTIONS
    style_read=p.get('action') in FACE_STYLE_READS
    eye_bag_action=p.get('action') in EYE_BAG_ACTIONS
    review_read=style_read or p.get('action') in EYE_BAG_READS or p.get('action') in ('face_decoration_alias_image','face_decoration_support_alias_image')
    echo={'face_style_request':deepcopy({key:p.get(key) for key in ('action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')})} if style_action else {}
    if p.get('action') in ('face_decoration_reference','face_decoration_review'):
        echo={'face_decoration_request':deepcopy({key:p.get(key) for key in ('action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')})}
    if p.get('action') in DECORATION_ALIAS_ACTIONS:
        echo={'face_decoration_alias_request':deepcopy({key:p.get(key) for key in ('action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')})}
    if p.get('action') in DECORATION_SUPPORT_ALIAS_ACTIONS:
        echo={'face_decoration_support_alias_request':deepcopy({key:p.get(key) for key in ('action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')})}
    if eye_bag_action:
        echo={'eye_bag_request':deepcopy({key:p.get(key) for key in ('action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')})}
    digest=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='cmd'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    if old.get('digest') not in (None,digest):
        emit({'event':'people_result','protocol':1,'action':p.get('action'),'request_id':p['request_id'],'document_id':p.get('document_id'),
              'success':False,'error':'People request identity was reused with different content','outcome_unknown':False,
              **({'outcome_unknown':True,'no_write':False,'rolled_back':False,'requires_reload':False} if p.get('action') in DECORATION_SUPPORT_ALIAS_ACTIONS else {}),
              **echo,**({} if review_read or p.get('action') in DECORATION_SUPPORT_ALIAS_ACTIONS else {'doc_state':engine.doc_state()})});return
    if 'result' in old:emit(old['result']);return
    if p.get('action') in EYE_BAG_READS:
        from .eye_bag_review_jobs import controller
        controller(engine).retire(p['request_id'])
    # Publication can succeed before status emission or history recording fails.
    # Rollback also advances the graph fence; neither case is a proven refusal.
    guarded_review=style_action or eye_bag_action or p.get('action') in DECORATION_ACTIONS
    owner=engine.__dict__.get('_people_graph_owner') if guarded_review else None
    fence_changed=(old.get('before_fence') is not None and
                   ((owner is None or owner.fence!=old['before_fence']) if guarded_review else engine._people_owner().fence!=old['before_fence']))
    proven_cancel=(old.get('eye_bag_cancelled') is True and p.get('action') in EYE_BAG_READS
        and old.get('before_fence') is not None and not fence_changed
        and not old.get('side_effects_started') and not old.get('success') and not old.get('frame_emitted'))
    # A completed read unwind cannot publish, even if its display pipeline has
    # since disappeared. Never apply this proof to writes or a changed fence.
    unknown=False if proven_cancel else (engine._vram is None or bool(error and
        (old.get('success') or old.get('side_effects_started') or fence_changed)))
    support_action=p.get('action') in DECORATION_SUPPORT_ALIAS_ACTIONS
    support_rollback=bool(support_action and error and old.get('rolled_back') and not old.get('requires_reload'))
    if support_rollback:unknown=False
    result={'event':'people_result','protocol':1,'action':p.get('action'),'request_id':p['request_id'],'document_id':p.get('document_id'),
        'success':bool(old.get('success')) and not error,'error':error,'outcome_unknown':unknown,
        'created_id':old.get('created_id'),'batch_id':old.get('batch_id'),'frame_emitted':old.get('frame_emitted',False),**echo}
    if support_action:
        result.update(no_write=not unknown and not old.get('side_effects_started') and not fence_changed,
            rolled_back=support_rollback,requires_reload=bool(old.get('requires_reload')))
        marker=old.get('face_decoration_support_alias_review');members=old.get('alias_members')
        if marker is not None and members is not None and old.get('batch_id') is not None:
            result.update(face_decoration_support_alias_review=deepcopy(marker),alias_members=deepcopy(members),module_scope=['lnx.people_graph.v1'])
    if proven_cancel:
        result.update(success=False,eye_bag_cancelled=True,error=error or 'Eye-bag read stopped after cancellation')
        old.pop('payload',None)
        result.pop('batch_id',None);result.pop('created_id',None)
    if 'payload' in old:result['payload']=old['payload']
    if old.get('payload_released'):result['payload_released']=True
    if engine._vram is not None and not review_read and not (support_action and not result['success']):
        try:result['doc_state']=engine.doc_state()
        except Exception as state_error:
            result.update(success=False,outcome_unknown=True,
                error=f"{error or 'People result state unavailable'}; {type(state_error).__name__}: {state_error}")
            if support_action:result.update(no_write=False,rolled_back=False)
    if support_action and not result['success']:
        # Failed previews and attempted confirmations are never publication
        # evidence. Preserve only verified terminal/uncertain ledger diagnostics.
        result.pop('payload',None);result.pop('doc_state',None);result.pop('payload_released',None)
    records[p['request_id']]={'result':result,'digest':digest}
    from .face_decoration_host import bound_receipt_images
    bound_receipt_images(records)
    from .skin_colour_body_host import bound_receipt_payloads
    bound_receipt_payloads(records)
    # Readback PNGs are session display pages, not durable outcome records.
    # Retain at most two; old request identities remain replayable without pixels.
    remaining=2;decoration_alias_remaining=2;decoration_support_alias_remaining=2
    eye_bag_remaining=3;eye_bag_reference_remaining=1;eye_bag_crop_remaining=2
    for row in reversed(records.values()):
        saved=row.get('result',row);body=saved.get('payload')
        if type(body) is dict and body.get('kind')=='face_decoration_support_alias_image':
            if decoration_support_alias_remaining:decoration_support_alias_remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
        elif type(body) is dict and body.get('kind')=='face_decoration_alias_image':
            if decoration_alias_remaining:decoration_alias_remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
        elif type(body) is dict and body.get('kind')=='face_style_image':
            if remaining:remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
        elif type(body) is dict and body.get('kind')=='eye_bag_image':
            if eye_bag_remaining:eye_bag_remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
        elif type(body) is dict and body.get('kind')=='eye_bag_source_image':
            if eye_bag_crop_remaining:eye_bag_crop_remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
        elif type(body) is dict and body.get('kind')=='eye_bag_reference':
            if eye_bag_reference_remaining:eye_bag_reference_remaining-=1
            else:saved.pop('payload',None);saved['payload_released']=True
    while len(records)>128:records.popitem(last=False)
    emit(result)


def legacy(engine,operation,p,emit):
    context=p.get('people_context')
    if type(context) is not dict or set(context)!={'document_id','document_epoch','document_revision','state_revision','association_revision','target'}:raise ValueError('Portrait mutation requires its captured people target and document fences')
    envelope={**context,'request_id':uuid.uuid4().hex};state,binding,target=checked(engine,envelope)
    if target!=engine._people_targets.get(binding['asset_sha256']):raise ValueError('Portrait editing scope changed after this gesture')
    patches=[]
    if operation in (*A.GEOMETRY,A.LIP):
        field={op:key for op,key in zip(A.GEOMETRY,('brow_shape','nose_shape','eye_shape','mouth_shape'))}.get(operation,'lip_makeup')
        if p.get('document_id')!=engine._load_id:raise ValueError('Portrait document view changed')
        expected={'cmd','recipe','document_id','control','people_context'}|({'base'} if operation!=A.LIP else set())
        if set(p)!=expected or p.get('recipe') is None:raise ValueError('Invalid portrait gesture fields')
        if operation!=A.LIP and p.get('base') is None:raise ValueError('Portrait base is required')
        neutral,validator=A.specifications()[operation]
        if p.get('control') not in (*neutral.keys(),'all') or p.get('control')=='version':raise ValueError('Unknown portrait control')
        previous=validator(getattr(engine,'_'+field));value=validator(p.get('recipe'))
        if operation!=A.LIP and validator(p.get('base'))!=previous:raise ValueError('Portrait base changed; no newer intent was overwritten')
        if operation==A.LIP and p.get('control')!='all':
            control=p.get('control')
            if control not in previous or control=='version':raise ValueError('Unknown lip control')
            value={**previous,control:value[control]}
        old=A.leaves(previous)
        patches=[{'operation_id':operation,'parameter_path':path,'value':value,'unset':False} for path,value in A.leaves(value).items() if old[path]!=value]
    else:
        action=p.get('action','set')
        if operation==A.DEFORM:
            given=p.get('amounts') or {};known=A.defaults()[A.DEFORM]
            if action in ('clear','inherit'):given={path[1:]:0. for path in known}
            if action not in ('set','clear','inherit'):raise ValueError('Unknown deform mutation')
            patches=[{'operation_id':operation,'parameter_path':'/'+key,**({'unset':True} if action=='inherit' else {'unset':False,'value':value})} for key,value in given.items()]
        else:
            from .ops import enhance as H
            from . import facial_wrinkle_state as W
            if action not in ('set','clear'):raise ValueError('Unknown enhance mutation')
            given={key:p[key] for key in H.AMOUNT_KEYS if key in p}
            if action=='clear':given=H.check_amounts({})
            patches=[{'operation_id':A.WRINKLES if key in W.INTENT_KEYS else A.ENHANCE,'parameter_path':'/'+key,'value':value,'unset':False} for key,value in given.items()]
    if patches:
        source=engine._people_source();command={**envelope,'action':'patch','payload':{'patches':patches}}
        result=EDIT.stage(command,state,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},asset_sha256=binding['asset_sha256'],source_dimensions=(source['width'],source['height']))
        _,frame=publish(engine,state,result['state'],envelope['request_id'],shared=target['scope'] in ('person','group'))
    else:frame=engine._write_current_frame('people_unchanged')
    if frame is not None:frame['doc_state']=engine.doc_state();emit(frame)
    if operation==A.LIP:emit({'event':'lip_makeup_done','document_id':engine._load_id,'recipe':engine._lip_makeup,'facts':{}})
    if operation==A.DEFORM:engine._emit_deform_state('set')
    if operation==A.ENHANCE:engine._emit_enhance_state('set')
