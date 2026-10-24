# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-face recipe composition with real immutable full-source review.

No new pixel algorithm, source analysis, history owner or implicit migration.
Only existing canonical parameter leaves are published by the people owner.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import re
import time
import uuid

from . import face_style_recipes as RECIPES
from . import people_state as S, people_algorithms as A
from . import creative_derived_source as SOURCE
from .portrait_review_render import image as render_image, snapshot_key

MAX_REVIEWS = 8
TTL = 1800
ACTIONS = ('face_style_catalog','face_style_preview','face_style_image','face_style_confirm')


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def check_action(action,payload,target):
    if (action not in ACTIONS or type(payload) is not dict or type(target) is not dict
            or set(target)!={'scope','target_id','face_ref'} or target.get('scope')!='face'):
        raise ValueError('Face styles require one explicit current face, never an inferred person or group')
    ref=S.check_ref(target.get('face_ref'))
    if target['target_id']!=ref['face_instance_id']:raise ValueError('Face-style target and FaceRef differ')
    if action=='face_style_catalog':
        if payload:raise ValueError('Face-style catalogue accepts no recipe')
    elif action=='face_style_preview':
        if set(payload)!={'version','style','amount'} or type(payload['version']) is not int or payload['version']!=1:
            raise ValueError('Face-style preview needs its exact versioned scalar recipe')
        RECIPES.patches(payload['style'],payload['amount'])
    else:
        fields={'token','side','sha256'} if action=='face_style_image' else {'token','ack'}
        if set(payload)!=fields or type(payload['token']) is not str or re.fullmatch('[0-9a-f]{32}',payload['token']) is None:
            raise ValueError('Face-style review requires its exact session token')
        if action=='face_style_image':
            if payload['side'] not in ('before','after') or not _hash(payload['sha256']):raise ValueError('Invalid face-style image identity')
        else:
            ack=payload['ack']
            if type(ack) is not dict or set(ack)!={'review_sha256','before_sha256','after_sha256'} or not all(_hash(v) for v in ack.values()):
                raise ValueError('Face-style confirmation requires the complete loaded image pair')


def _store(engine):
    store=engine.__dict__.get('_face_style_reviews')
    if store is None:
        # Reuse immutable blob storage, not a collarbone controller or proof.
        from .collarbone_visual_store import _Images
        store={'pending':OrderedDict(),'images':_Images(records=lambda plan:plan.records)}
        engine._face_style_reviews=store
    now=time.monotonic()
    for token,entry in list(store['pending'].items()):
        if now>=entry['expires']:del store['pending'][token]
    store['images'].prune({token:entry for token,entry in store['pending'].items() if not entry['claimed']})
    return store


def _live(engine,state,target):
    from .people_preset_plan import require_active_owner
    from .virtual_copy_people import current_row,scope_rows
    owner=require_active_owner(engine);row=current_row(engine)
    if owner.snapshot()!=state:raise ValueError('Face-style graph changed')
    ref=S.check_ref(target['face_ref']);face=state['faces'].get(target['target_id'])
    if face is None or not face['enabled'] or S.face_ref(face)!=ref:
        raise ValueError('Face-style target is disabled, missing or has another analysis')
    current=engine._people_preset_capture()
    proof=SOURCE.row_proof({**row,'state':current})
    if ref['asset_sha256']!=proof['asset_sha256']:
        raise ValueError('Face style cannot borrow original-image analysis for another effective source')
    if (engine._people_cursors.get(proof['asset_sha256'])!=target['target_id']
            or engine._people_targets.get(proof['asset_sha256'])!=target):
        raise ValueError('Face style requires the explicitly selected current face')
    # One photograph's review must not authorize unseen same-source aliases.
    aliases=[other for other in scope_rows(engine) if SOURCE.row_asset({**other,'state':current} if other is row else other)==proof['asset_sha256']]
    if len(aliases)!=1 or aliases[0] is not row:
        raise ValueError('This face is shared by multiple source-identical documents; use an independent virtual copy or reviewed cross-image transfer')
    version=engine._document_versions().version(row)
    return owner,row,current,proof,version


def catalogue(engine,state,target,payload):
    check_action('face_style_catalog',payload,target);_live(engine,state,target)
    return {'kind':'face_style_catalog','catalogue':RECIPES.catalogue()}


def _plan(token,review):
    visual=review['visual']
    return SimpleNamespace(token=token,records={visual['document_id']:visual})


def _ack(review):
    visual=review['visual']
    return {'review_sha256':review['review_sha256'],'before_sha256':visual['before']['sha256'],'after_sha256':visual['after']['sha256']}


def _entry(engine,token):
    store=_store(engine);entry=store['pending'].get(token)
    if entry is None:raise ValueError('Face-style review expired or was replaced; preview again')
    return store,entry


def _verify(engine,state,target,entry):
    owner,row,current,source,version=_live(engine,state,target)
    review=entry['review']
    if (entry['claimed'] or owner is not entry['owner'] or owner.fence!=entry['fence']
            or row is not entry['row'] or row['path']!=entry['path'] or engine._load_id!=entry['load_id']
            or version.document_id!=review['visual']['document_id'] or str(version.revision)!=review['visual']['revision']
            or target!=entry['target'] or source!=review['owner']['source_proof']
            or state!=entry['before'] or snapshot_key(engine,row,current,state)!=entry['before_key']
            or snapshot_key(engine,row,current,entry['candidate'])!=entry['after_key']):
        raise ValueError('Face-style source, repair, target, support or complete recipe changed; preview again')
    SOURCE.verify_row({**row,'state':current},source)
    return current


def preview(engine,state,target,payload):
    from .people_edit import stage
    from .people_resolver import resolve
    from .people_transfer_inventory import proof
    check_action('face_style_preview',payload,target)
    owner,row,current,source,version=_live(engine,state,target);fence=owner.fence
    patches=RECIPES.patches(payload['style'],payload['amount'])
    binding=engine._people_binding()
    command={**{key:binding[key] for key in ('document_id','document_epoch','document_revision')},
        'state_revision':state['revision'],'association_revision':state['association_revision'],
        'request_id':uuid.uuid4().hex,'target':deepcopy(target),'action':'patch','payload':{'patches':patches}}
    owned=SOURCE.binding(current,row['path'],(row['src_w'],row['src_h']))
    result=stage(command,state,**{key:binding[key] for key in ('document_id','document_epoch','document_revision')},
        asset_sha256=source['asset_sha256'],source_dimensions=(owned['width'],owned['height']))
    candidate=result['state']
    if SOURCE.record(current) is not None:
        from .creative_derived_effects import require_graph
        require_graph(candidate,SOURCE.binding(current),document_id=version.document_id)
    RECIPES.validate_compatibility(A.recipes(resolve(candidate,target['target_id'],A.defaults())))
    before_key=snapshot_key(engine,row,current,state);after_key=snapshot_key(engine,row,current,candidate)
    a,left,proof_a=render_image(engine,row,current,state,version.document_id,version.revision)
    b,right,proof_b=render_image(engine,row,current,candidate,version.document_id,version.revision)
    if proof_a['source_proof']!=source or proof_b['source_proof']!=source or proof_a['source_size']!=proof_b['source_size']:
        raise ValueError('Face-style image pair changed effective source')
    token=uuid.uuid4().hex
    visual={'version':1,'document_id':version.document_id,'revision':str(version.revision),'source_proof':source,
        'before_state_sha256':proof_a['candidate_sha256'],'candidate_state_sha256':proof_b['candidate_sha256'],
        'before_people_sha256':proof_a['people_sha256'],'candidate_people_sha256':proof_b['people_sha256'],
        'source_size':proof_a['source_size'],'before_output_size':proof_a['output_size'],'after_output_size':proof_b['output_size'],
        'before':a,'after':b}
    review={'version':1,'token':token,'recipe':deepcopy(payload),'owner':proof(engine,row,state,source_row={**row,'state':current}),
        'face_ref':deepcopy(target['face_ref']),'patches_sha256':digest(patches),'visual':visual}
    review['review_sha256']=digest(review)
    entry={'owner':owner,'row':row,'path':row['path'],'load_id':engine._load_id,'fence':fence,'target':deepcopy(target),
        'before':deepcopy(state),'candidate':candidate,'before_key':before_key,'after_key':after_key,
        'review':review,'expires':time.monotonic()+TTL,'claimed':False}
    _verify(engine,state,target,entry)
    store=_store(engine)
    while len(store['pending'])>=MAX_REVIEWS:store['pending'].popitem(last=False)
    store['images'].prune(store['pending'])
    store['images'].attach(_plan(token,review),{version.document_id:{'revision':str(version.revision),'before':left,'after':right}})
    store['pending'][token]=entry
    return {'kind':'face_style_preview','review':deepcopy(review)}


def image(engine,state,target,payload):
    check_action('face_style_image',payload,target);store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    review=entry['review'];visual=review['visual'];side=payload['side']
    if payload['sha256']!=visual[side]['sha256']:raise ValueError('Face-style image hash does not match review')
    pixels=store['images'].read(_plan(payload['token'],review),visual['document_id'],visual['revision'],side,payload['sha256'])
    _verify(engine,state,target,entry)
    return {'kind':'face_style_image',**deepcopy(payload),'review_sha256':review['review_sha256'],'image':pixels}


def confirm(engine,state,target,payload):
    check_action('face_style_confirm',payload,target);store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    review=entry['review'];visual=review['visual']
    if payload['ack']!=_ack(review):raise ValueError('Confirm this exact full face-style image pair')
    for side in ('before','after'):
        store['images'].read(_plan(payload['token'],review),visual['document_id'],visual['revision'],side,visual[side]['sha256'])
    _verify(engine,state,target,entry)
    proof={'kind':'face_style_confirm','token':payload['token'],'review_sha256':review['review_sha256'],
           'ack':deepcopy(payload['ack']),'recipe':deepcopy(review['recipe']),'patches_sha256':review['patches_sha256']}
    return deepcopy(entry['candidate']),proof


def verify_before_publish(engine,state,target,payload,candidate,proof):
    _,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    review=entry['review']
    current=engine._people_preset_capture()
    if SOURCE.record(current) is not None:
        from .creative_derived_effects import require_graph
        require_graph(candidate,SOURCE.binding(current),document_id=review['visual']['document_id'])
    if (candidate!=entry['candidate'] or proof.get('review_sha256')!=review['review_sha256']
            or proof.get('token')!=payload['token'] or proof.get('ack')!=_ack(review)):
        raise ValueError('Face-style publication differs from the reviewed graph')
    entry['claimed']=True


def verify_after_publish(engine,candidate,proof):
    from .people_preset_plan import require_active_owner
    from .virtual_copy_people import current_row
    _,entry=_entry(engine,proof['token']);owner=require_active_owner(engine);row=current_row(engine)
    review=entry['review'];version=engine._document_versions().version(row)
    current=engine._people_preset_capture()
    if (not entry['claimed'] or owner is not entry['owner'] or owner.fence!=entry['fence']+1
            or row is not entry['row'] or row['path']!=entry['path'] or engine._load_id!=entry['load_id']
            or version.document_id!=review['visual']['document_id'] or version.revision!=int(review['visual']['revision'])+1
            or candidate!=entry['candidate'] or snapshot_key(engine,row,current,owner.snapshot())!=entry['after_key']):
        raise ValueError('Face-style publication differs from full reviewed source/graph; reload or inspect the existing request')
    SOURCE.verify_row({**row,'state':current},review['owner']['source_proof'])
