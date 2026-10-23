"""Reachable document-bound people edits, existing history and batch receipts."""
from collections import OrderedDict
from copy import deepcopy
import uuid
import hashlib
import json
from . import people_state as S,people_algorithms as A,people_edit as EDIT
from .people_command import validate_envelope
from .people_graph_owner import affected_assets


def checked(engine,p):
    why=engine._guard_editable('people')
    if why:raise ValueError(why)
    engine._people_bind();binding=engine._people_binding();state=engine._people_owner().snapshot()
    target=validate_envelope(p,state,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')})
    asset=binding['asset_sha256']
    if (target['scope']=='face' and target['face_ref']['asset_sha256']!=asset) or (target['scope']=='all_people' and target['target_id']!=asset):
        raise ValueError('People command targets another source asset')
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


def publish(engine,before,candidate,request_id,*,shared=False):
    assets=affected_assets(before,candidate);assets.add(engine._people_source()['sha256'])
    if shared:
        from .people_batch_ledger import commit
        result=commit(engine._batch_controller(),engine,before,candidate,request_id=request_id)
        return result if result else (None,None)
    engine._people_prepare_graph(candidate,assets)
    return None,engine._people_publish_graph(candidate,assets)


def analyse(engine,state,face_ref):
    from types import SimpleNamespace
    from . import face as F,people_binding as B,people_associations as G,people_retained_analysis as RA
    from .nose_shape_runtime import exclusion
    from .facial_wrinkle_runtime import skin_support
    import numpy as np
    face=state['faces'][face_ref['face_instance_id']];source=engine._people_source()
    if face['local_assets']:raise ValueError('Reanalysis cannot silently rebind existing source-owned recovery; retain it and review explicitly')
    with F.MediaPipeFace() as backend:
        points,_=F.detect_region(backend,engine._src_rgb,face['box'])
        pc=SimpleNamespace(backend='mediapipe',detector_model_sha256=backend.detector_model_sha256,semantic_model_sha256=backend.semantic_model_sha256)
        evidence=B.evidence(pc,points,(source['width'],source['height']))
        original=engine._precompute
        if original is None:
            original=F.FacePrecompute(landmarks=points,masks=backend.semantic_masks(engine._src_rgb),backend='mediapipe',
                t_detect_ms=0.,t_masks_ms=0.,face_box=tuple(face['box']),all_landmarks=[points],manual=(0,),
                detector_model_sha256=backend.detector_model_sha256,semantic_model_sha256=backend.semantic_model_sha256)
            engine._precompute=original;engine._precompute_backend='mediapipe'
        if original.semantic_model_sha256!=evidence['semantic_model_sha256']:
            raise ValueError('Region analysis lacks matching full-source semantic evidence')
    out=G.reanalyse(state,source['sha256'],{face_ref['face_instance_id']:evidence},expected_revision=state['revision'],user_confirmed=True)
    ref=S.face_ref(out['faces'][face_ref['face_instance_id']]);points=np.array(points,dtype='<f4',copy=True);points.setflags(write=False)
    row={'face_ref':ref,'evidence':evidence,'landmarks':points,'excluded':exclusion(original),'skin':skin_support(original)}
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
    if action=='lipstick_palette':
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
        if action=='analyse_face':
            if payload!={} or target['scope']!='face':raise ValueError('Region analysis needs an explicit face')
            records[request]['side_effects_started']=True
            candidate,ref=analyse(engine,state,target['face_ref'])
            target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
        elif action=='lipstick_review':
            from .lipstick_host import stage_review
            candidate=stage_review(engine,state,target,payload)
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
        else:batch_id,frame=publish(engine,state,candidate,request,shared=shared)
        if action=='analyse_face':select(engine,engine._people_owner().snapshot(),asset,target)
        if frame is not None:frame['doc_state']=engine.doc_state()
    if frame is not None:emit(frame)
    records[request].update(success=True,frame_emitted=frame is not None,created_id=created,batch_id=batch_id)
    while len(records)>128:records.popitem(last=False)


def finish(engine,p,error,emit):
    if type(p.get('request_id')) is not str:return
    records=engine.__dict__.setdefault('_people_receipts',OrderedDict());old=records.get(p['request_id'],{})
    digest=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='cmd'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    if old.get('digest') not in (None,digest):
        emit({'event':'people_result','protocol':1,'action':p.get('action'),'request_id':p['request_id'],'document_id':p.get('document_id'),
              'success':False,'error':'People request identity was reused with different content','outcome_unknown':False,'doc_state':engine.doc_state()});return
    if 'result' in old:emit(old['result']);return
    # Publication can succeed before status emission or history recording fails.
    # Rollback also advances the graph fence; neither case is a proven refusal.
    fence_changed=(old.get('before_fence') is not None and
                   engine._people_owner().fence!=old['before_fence'])
    unknown=engine._vram is None or bool(error and
        (old.get('success') or old.get('side_effects_started') or fence_changed))
    result={'event':'people_result','protocol':1,'action':p.get('action'),'request_id':p['request_id'],'document_id':p.get('document_id'),
        'success':bool(old.get('success')) and not error,'error':error,'outcome_unknown':unknown,
        'created_id':old.get('created_id'),'batch_id':old.get('batch_id'),'frame_emitted':old.get('frame_emitted',False)}
    if engine._vram is not None:
        try:result['doc_state']=engine.doc_state()
        except Exception as state_error:
            result.update(success=False,outcome_unknown=True,
                error=f"{error or 'People result state unavailable'}; {type(state_error).__name__}: {state_error}")
    records[p['request_id']]={'result':result,'digest':digest}
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
