"""Immutable vector recovery assets; face history stores only content references.

The host persists this project-level asset map alongside the canonical graph.
Assets are append-only here so undo/reopen can still resolve old references.
Raster coverage is rebuilt at requested source dimensions, not enlarged from a
proxy mask. Original legacy recovery records are never deleted or rebound.
"""
from copy import deepcopy
import hashlib
import json
import numpy as np
from . import people_state as S, effect_recovery_state as R, local_mask_recipe as M
from .facial_wrinkle_recovery import FACE_TARGETS


def content_digest(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def retain(state,assets,face_ref,source,row):
    """Caller has a reviewed face; old source/landmark ownership must still agree."""
    state=S.check(state);ref=S.check_ref(face_ref);face=state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref:raise ValueError('Recovery target face changed')
    checked=R.check({'version':R.VERSION,'source':source,'targets':[row]})
    row=checked['targets'][0]
    if row['target'] not in FACE_TARGETS:raise ValueError('Only face-owned recovery belongs in this store')
    owner=row['owner'];evidence=face['evidence']
    if evidence['status']!='verified':raise ValueError('Recovery requires verified retained face evidence')
    if owner['source_sha256']!=ref['asset_sha256'] or owner['landmarks_sha256']!=evidence['landmark_digest'] or owner['backend']!=evidence['backend']:
        raise ValueError('Recovery intent belongs to another retained source analysis')
    if (source['width'],source['height'])!=(evidence['source_width'],evidence['source_height']):
        raise ValueError('Recovery source dimensions differ from retained face evidence')
    record={'version':1,'face_ref':ref,'source':checked['source'],'row':row}
    digest=content_digest(record);out=deepcopy(assets)
    if digest in out and out[digest]!=record:raise ValueError('Recovery asset hash collision')
    out[digest]=record
    descriptor={'owner':ref,'content_sha256':digest,'kind':row['target']}
    if face['local_assets'].get(row['target'])==descriptor:return state,out
    state['faces'][ref['face_instance_id']]['local_assets'][row['target']]=descriptor
    state['revision']+=1
    return S.check(state),out


def migrate_legacy(state,assets,value):
    """Exact old source+landmark proof only; ambiguous rows remain untouched."""
    state=S.check(state);value=R.check(value);out=deepcopy(assets);unresolved=[]
    # Clearing the active reference must not resurrect an old global row on
    # the next synchronization. Its archived intent and immutable bytes remain.
    source=value['source']
    if source is not None and any(record['legacy_key']=='_effect_recovery'
            and record['asset_sha256']==source['sha256'] and record['status']!='unresolved'
            for record in state['unresolved_legacy']):
        return state,out,unresolved
    for row in value['targets']:
        if row['target'] not in FACE_TARGETS:continue
        owner=row['owner']
        matches=[face for face in state['faces'].values() if face['asset_sha256']==owner['source_sha256']
                 and face['evidence']['landmark_digest']==owner['landmarks_sha256'] and face['evidence']['backend']==owner['backend']]
        if len(matches)!=1:
            unresolved.append({'target':row['target'],'reason':'Recovery has no unique retained face evidence'});continue
        face=matches[0]
        if row['target'] in face['local_assets']:continue # Never overwrite later user recovery edits on reload.
        old={'version':1,'face_ref':S.face_ref(face),'source':value['source'],'row':row}
        if content_digest(old) in out:
            # Another legacy family may still be unresolved. A deliberately
            # detached, already retained row must not be reimported meanwhile.
            if out[content_digest(old)]!=old:raise ValueError('Recovery asset hash collision')
            continue
        state,out=retain(state,out,S.face_ref(face),value['source'],row)
    if not unresolved:
        for record in state['unresolved_legacy']:
            if record['legacy_key']=='_effect_recovery' and record['intent']==value and record['status']=='unresolved':
                record['status']='retained';state['revision']+=1
    return S.check(state),out,unresolved


def resolve(state,assets,face_ref,target):
    """Resolve only this exact current face's immutable vector reference."""
    ref=S.check_ref(face_ref);face=state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref:raise ValueError('Recovery target face changed')
    if target not in FACE_TARGETS:raise ValueError('No face-owned recovery consumer for this target')
    descriptor=face['local_assets'].get(target)
    if descriptor is None:return None
    key=descriptor['content_sha256'];record=assets.get(key)
    if (record is None or content_digest(record)!=key or record['face_ref']!=ref
            or descriptor!={'owner':ref,'content_sha256':key,'kind':target}):
        raise ValueError('Retained recovery vector is missing, changed or owned by another face')
    checked=R.check({'version':R.VERSION,'source':record['source'],'targets':[record['row']]})
    row=checked['targets'][0];evidence=face['evidence'];owner=row.get('owner')
    if (row['target']!=target or checked['source']['sha256']!=ref['asset_sha256']
            or owner['landmarks_sha256']!=evidence['landmark_digest']
            or owner['backend']!=evidence['backend'] or evidence['status']!='verified'
            or (checked['source']['width'],checked['source']['height'])
            !=(evidence['source_width'],evidence['source_height'])):
        raise ValueError('Recovery vector does not match retained source and landmark evidence')
    return checked


def detach(state,face_ref,target):
    """Remove an active pointer, never immutable bytes needed by undo/reopen."""
    out=S.check(state);ref=S.check_ref(face_ref);face=out['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref:raise ValueError('Recovery target face changed')
    if target not in FACE_TARGETS:raise ValueError('No face-owned recovery consumer for this target')
    if target in face['local_assets']:
        del face['local_assets'][target];out['revision']+=1
    return S.check(out)


def raster(state,assets,asset_sha256,shape):
    """Produces exact owner-pinned fields for people_render_runtime.prepare."""
    state=S.check(state);S.digest(asset_sha256);result={};rows=[];work=0
    for face in state['faces'].values():
        if face['asset_sha256']!=asset_sha256 or not face['enabled']:continue
        for target,descriptor in face['local_assets'].items():
            if target in ('skin_colour_body_visibility','hair_colour','eye_light_visibility','blush_makeup_visibility','lipstick_visibility','eyeliner_visibility','eyelash_visibility','brow_makeup_visibility','iris_makeup_visibility'):continue # Dedicated support consumers, never facial recovery.
            checked=resolve(state,assets,S.face_ref(face),target);row=checked['targets'][0]
            work+=M.validate_budget(row['recipe'],shape)['work'] if row['enabled'] else 0
            rows.append((face,row,descriptor['content_sha256']))
    if len(rows)*shape[0]*shape[1]>R.MAX_MASK_PIXELS or work>M.MAX_WORK:
        raise ValueError('All-face recovery exceeds the aggregate raster budget')
    for face,row,key in rows:
        weight=M.raster(row['recipe'],shape) if row['enabled'] else np.zeros(shape,np.uint8)
        weight=np.ascontiguousarray(weight,dtype=np.uint8);weight.setflags(write=False)
        result[(face['face_instance_id'],row['target'])]={'face_ref':S.face_ref(face),'stage':row['target'],
            'weight':weight,'content_sha256':hashlib.sha256(weight.tobytes()).hexdigest(),'recipe_sha256':key}
    return result


def check_store(assets):
    if type(assets) is not dict or len(assets)>4096:
        raise ValueError('Invalid or oversized portrait recovery asset store')
    if len(json.dumps(assets,allow_nan=False).encode())>16*1024*1024:
        raise ValueError('Portrait recovery vector assets exceed the project budget')
    for key,record in assets.items():
        S.digest(key)
        if type(record) is not dict or set(record)!={'version','face_ref','source','row'} or record['version']!=1 or content_digest(record)!=key:
            raise ValueError('Portrait recovery asset content hash/schema mismatch')
        ref=S.check_ref(record['face_ref'])
        if record.get('row',{}).get('target')=='skin_colour_body_visibility':
            from .skin_colour_body_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='iris_makeup_visibility':
            from .iris_makeup_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='eyeliner_visibility':
            from .eyeliner_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='eyelash_visibility':
            from .eyelash_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='brow_makeup_visibility':
            from .brow_makeup_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='lipstick_visibility':
            from .lipstick_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='blush_makeup_visibility':
            from .blush_makeup_support import check_record
            check_record(record)
            continue
        if record.get('row',{}).get('target')=='eye_light_visibility':
            from .eye_light_support import check_record
            check_record(record)
            continue
        checked=R.check({'version':R.VERSION,'source':record['source'],'targets':[record['row']]})
        if checked['source']['sha256']!=ref['asset_sha256'] or checked['targets'][0]['target'] not in FACE_TARGETS:
            raise ValueError('Portrait recovery asset source or operator is invalid')
    return deepcopy(assets)
