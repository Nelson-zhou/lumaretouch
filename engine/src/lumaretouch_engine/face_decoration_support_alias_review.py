# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete visible-support alias review, separate from scalar authority. UNRUN.

Every source-identical document is rendered with its own complete recipe and
repair. The proposed immutable support bank remains detached until the existing
ledger publishes the exact graph/bank transaction. No pixels become supports.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import re
import time
import uuid
from . import people_state as S, face_decoration_support as SUPPORT
from . import face_decoration_alias_review as SCALAR, face_style_alias_review as CLOSURE
from . import face_decoration_support_alias_plan as PLAN
from . import creative_derived_source as SOURCE, collarbone_transfer_review as VISUAL
from .portrait_review_render import image as render_image, snapshot_key

READS=frozenset(('face_decoration_support_alias_preview','face_decoration_support_alias_image'))
ACTIONS=READS|{'face_decoration_support_alias_confirm'}
TTL=1800
MAX_REVIEWS=4


def read_only(message):
    """Even a malformed preview/image cannot become a recovery mutation."""
    return (type(message) is dict and message.get('cmd')=='people'
        and type(message.get('action')) is str and message['action'] in READS)


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def check_action(action,payload,target):
    from .face_decoration_host import check_proof
    if (action not in ACTIONS or type(payload) is not dict or type(target) is not dict
            or set(target)!={'scope','target_id','face_ref'} or target['scope']!='face'):
        raise ValueError('Support aliases require one explicitly selected retained face')
    ref=S.check_ref(target['face_ref'])
    if ref['face_instance_id']!=target['target_id']:raise ValueError('Support alias target differs from FaceRef')
    if action=='face_decoration_support_alias_preview':
        if set(payload)!={'region','reference_proof'}:raise ValueError('Support review requires only the exact shown source proof and painted region')
        SUPPORT.check_region(payload['region']);proof=check_proof(payload['reference_proof'])
        if proof['face_ref']!=ref:raise ValueError('Support reference belongs to another face')
    else:
        if type(payload.get('token')) is not str or re.fullmatch('[0-9a-f]{32}',payload['token']) is None:
            raise ValueError('Exact support alias review token required')
        if action=='face_decoration_support_alias_image':
            if set(payload)!={'token','document_id','side','sha256','review_sha256'} or payload['side'] not in ('before','after'):
                raise ValueError('Exact support alias image and complete review identity required')
            S.token(payload['document_id']);S.digest(payload['sha256']);S.digest(payload['review_sha256'])
        else:
            if set(payload)!={'token','ack'}:raise ValueError('Exact complete support alias acknowledgment required')
            CLOSURE.check_ack(payload['ack'])


def _store(engine):
    store=engine.__dict__.get('_face_decoration_support_alias_reviews')
    if store is None:
        from .collarbone_visual_store import _Images
        store={'pending':OrderedDict(),'images':_Images(records=lambda plan:plan.records)}
        engine._face_decoration_support_alias_reviews=store
    for token,entry in list(store['pending'].items()):
        if time.monotonic()>=entry['expires']:del store['pending'][token]
    store['images'].prune({token:entry for token,entry in store['pending'].items() if not entry['claimed']})
    return store


def _entry(engine,token):
    store=_store(engine);entry=store['pending'].get(token)
    if entry is None:raise ValueError('Support alias review expired; prepare and inspect every image again')
    return store,entry


def _plans(entry):
    return {'project':{'row':entry['row'],'before':entry['before'],'candidate':entry['candidate'],
        'reviewed_face_refs':deepcopy(entry['refs'])}}


def _plan(review):
    return SimpleNamespace(token=review['token'],records={m['visual']['document_id']:m['visual'] for m in review['members']})


def _ack(review):return CLOSURE._ack(review)


def _proof(review):
    return {'kind':'face_decoration_support_alias_confirm',
        **{key:deepcopy(review[key]) for key in ('token','review_sha256','target','face_ref','before_support_sha256','support_sha256',
            'before_bank_sha256','candidate_bank_sha256','candidate_state_revision')},
        'ack':_ack(review),'history_review_sha256':digest(_ack(review)),
        'alias_members':[{'document_id':m['visual']['document_id'],'expected_revision':m['visual']['revision'],
            'result_revision':str(int(m['visual']['revision'])+1)} for m in review['members']]}


def _snapshot(engine,row,recipe,entry,*,after):
    graph=entry['candidate'] if after else entry['before']
    context=PLAN.staged_context(engine,row,graph,entry['before_assets'],entry['assets']) if after else None
    return snapshot_key(engine,row,recipe,graph,staged_people_context=context)


def _verify(engine,state,target,entry):
    from .face_decoration_host import review_reference
    owner,row,current,source=SCALAR._live(engine,state,target);review=entry['review']
    if (engine._batch_controller() is not entry['batch'] or entry['claimed'] or owner is not entry['owner']
            or owner.fence!=entry['fence'] or row is not entry['row'] or engine._load_id!=entry['load_id']
            or state!=entry['before'] or target!=entry['target'] or source!=review['owner']['source_proof']
            or engine._document_versions().workspace!=entry['workspace'] or engine._people_support!=entry['before_assets']):
        raise ValueError('Support alias owner, graph, bank, source or session changed')
    review_reference(engine,state,target,{'region':review['region'],'reference_proof':review['reference_proof']})
    PLAN.narrow(state,entry['candidate'],entry['before_assets'],entry['assets'],target['face_ref'])
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256'])
    if len(members)!=len(entry['members']):raise ValueError('Support alias membership changed')
    own=PLAN.coverage(state,entry['candidate'],entry['before_assets'],entry['assets'],target['face_ref'])
    for actual,frozen in zip(members,entry['members']):
        other,recipe,proof,version=actual;visual=frozen['visual']
        if (other is not frozen['row'] or other['path']!=frozen['path'] or version.document_id!=visual['document_id']
                or str(version.revision)!=visual['revision'] or proof!=visual['source_proof'] or own!=frozen['coverage']
                or _snapshot(engine,other,recipe,entry,after=False)!=frozen['before_key']
                or _snapshot(engine,other,recipe,entry,after=True)!=frozen['after_key']):
            raise ValueError('Support alias source, repair, crop, support or complete member recipe changed')
        SOURCE.verify_row({**other,'state':recipe},proof)
    if CLOSURE._targets(engine,entry['batch'],_plans(entry),current)!=entry['targets']:
        raise ValueError('Support alias ledger closure changed')
    if (review['before_bank_sha256']!=digest(entry['before_assets']) or review['candidate_bank_sha256']!=digest(entry['assets'])
            or review['review_sha256']!=digest({key:value for key,value in review.items() if key!='review_sha256'})):
        raise ValueError('Support alias immutable bank or review digest changed')
    return current


def preview(engine,state,target,payload):
    from .face_decoration_host import review_reference
    from .people_transfer_inventory import proof
    check_action('face_decoration_support_alias_preview',payload,target)
    selected_source,ref,reference=review_reference(engine,state,target,payload)
    owner,row,current,source=SCALAR._live(engine,state,target)
    if selected_source['sha256']!=source['asset_sha256']:raise ValueError('Support reference changed effective source')
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    before_assets=deepcopy(engine._people_support)
    # Validate the real before before retaining paint. An active missing or
    # stale support is never made renderable by substituting the new bank.
    old_key=PLAN.visibility(state,before_assets,ref)
    candidate,assets=SUPPORT.retain(state,before_assets,ref,payload['region'])
    PLAN.narrow(state,candidate,before_assets,assets,ref)
    _,support=SUPPORT.resolve(candidate,assets,ref)
    coverage=PLAN.coverage(state,candidate,before_assets,assets,ref)
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256']);batch=engine._batch_controller()
    entry={'owner':owner,'row':row,'fence':owner.fence,'load_id':engine._load_id,
        'workspace':engine._document_versions().workspace,'batch':batch,'target':deepcopy(target),
        'before':deepcopy(state),'candidate':candidate,'before_assets':before_assets,'assets':assets,
        'refs':[item['face_ref'] for item in coverage['targets']],'members':[],'served':set(),'claimed':False}
    targets=CLOSURE._targets(engine,batch,_plans(entry),current)
    if {t['document_id'] for t in targets.values()}!={m[3].document_id for m in members} or len(targets)!=len(members):
        raise ValueError('Support alias ledger omits or adds affected documents')
    entry['targets']=deepcopy(targets);public=[];displays={};total=0;source_size=None
    for other,own,source_proof,version in members:
        if other is row and source_proof!=source:raise ValueError('Initiating support alias changed its exact original/derived provenance')
        before_key=_snapshot(engine,other,own,entry,after=False);after_key=_snapshot(engine,other,own,entry,after=True)
        context=PLAN.staged_context(engine,other,candidate,before_assets,assets)
        a,left,pa=render_image(engine,other,own,state,version.document_id,str(version.revision))
        b,right,pb=render_image(engine,other,own,candidate,version.document_id,str(version.revision),staged_people_context=context)
        total+=len(left['base64'])+len(right['base64'])
        if total>VISUAL.MAX_TOTAL_BASE64:raise ValueError('Support alias images exceed bounded preparation; no member or detail was omitted')
        if (pa['source_proof']!=source_proof or pb['source_proof']!=source_proof or pa['source_size']!=pb['source_size']
                or pa['output_size']!=pb['output_size'] or pa['source_size']!=[selected_source['width'],selected_source['height']]
                or (source_size is not None and source_size!=pa['source_size'])
                or _snapshot(engine,other,own,entry,after=False)!=before_key
                or _snapshot(engine,other,own,entry,after=True)!=after_key):
            raise ValueError('Support alias pair changed its immutable full source, crop or snapshot')
        source_size=pa['source_size']
        visual=VISUAL.checked({'version':1,'document_id':version.document_id,'revision':str(version.revision),
            'source_proof':source_proof,'before_state_sha256':pa['candidate_sha256'],'candidate_state_sha256':pb['candidate_sha256'],
            'before_people_sha256':pa['people_sha256'],'candidate_people_sha256':pb['people_sha256'],'source_size':source_size,
            'before_output_size':pa['output_size'],'after_output_size':pb['output_size'],'coverage_sha256':VISUAL.coverage_digest(coverage),
            'before':a,'after':b})
        public.append({'path':other['path'],'coverage':deepcopy(coverage),'visual':visual})
        entry['members'].append({'row':other,'path':other['path'],'coverage':deepcopy(coverage),'visual':visual,
            'before_key':before_key,'after_key':after_key})
        displays[version.document_id]={'revision':visual['revision'],'before':left,'after':right}
    token=uuid.uuid4().hex
    review={'version':1,'token':token,'target':SUPPORT.KIND,'owner':proof(engine,row,state,source_row={**row,'state':current}),
        'face_ref':deepcopy(ref),'before_support_sha256':old_key,'support_sha256':support,'reference_proof':reference,
        'region':deepcopy(payload['region']),'before_bank_sha256':digest(before_assets),'candidate_bank_sha256':digest(assets),
        'candidate_state_revision':candidate['revision'],'members':public}
    review['review_sha256']=digest(review);entry.update(review=review,expires=time.monotonic()+TTL)
    _verify(engine,state,target,entry);store=_store(engine)
    while len(store['pending'])>=MAX_REVIEWS:store['pending'].popitem(last=False)
    store['images'].prune(store['pending']);store['images'].attach(_plan(review),displays);store['pending'][token]=entry
    return {'kind':'face_decoration_support_alias_preview','review':deepcopy(review)}


def image(engine,state,target,payload):
    check_action('face_decoration_support_alias_image',payload,target)
    store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    review=entry['review'];visual=_plan(review).records.get(payload['document_id'])
    if (review['review_sha256']!=payload['review_sha256'] or visual is None
            or visual[payload['side']]['sha256']!=payload['sha256']):
        raise ValueError('Image is not a frozen support alias member')
    pixels=store['images'].read(_plan(review),payload['document_id'],visual['revision'],payload['side'],payload['sha256'])
    _verify(engine,state,target,entry);entry['served'].add((payload['document_id'],payload['side']))
    return {'kind':'face_decoration_support_alias_image',**deepcopy(payload),'image':pixels}


def _available(store,entry):
    review=entry['review'];plan=_plan(review)
    required={(document,side) for document in plan.records for side in ('before','after')}
    if entry['served']!=required:raise ValueError('Load every support alias before/after image before confirming')
    for visual in plan.records.values():
        for side in ('before','after'):
            store['images'].read(plan,visual['document_id'],visual['revision'],side,visual[side]['sha256'])


def confirm(engine,state,target,payload):
    check_action('face_decoration_support_alias_confirm',payload,target)
    store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    if payload['ack']!=_ack(entry['review']):raise ValueError('Acknowledge every support alias image pair in the exact frozen order')
    _available(store,entry);_verify(engine,state,target,entry)
    return deepcopy(entry['candidate']),_proof(entry['review'])


def publish(engine,state,target,payload,candidate,proof,request_id,mark_started=lambda:None):
    from .face_decoration_support_alias_transaction import commit
    store,entry=_entry(engine,payload['token'])
    def verify_before():
        _verify(engine,state,target,entry)
        if candidate!=entry['candidate'] or proof!=_proof(entry['review']) or payload['ack']!=_ack(entry['review']):
            raise ValueError('Support publication differs from the exact reviewed graph, bank or acknowledgment')
        _available(store,entry)
    def claim():
        mark_started();entry['claimed']=True
    verify_before()
    entry['batch'].documents.remember_current();verify_before()
    try:
        result=commit(engine,review=entry['review'],plans=_plans(entry),targets=deepcopy(entry['targets']),
            before_assets=entry['before_assets'],after_assets=entry['assets'],ack=payload['ack'],request_id=request_id,
            verify_before=verify_before,mark_started=claim)
        if result is None:raise ValueError('Support alias publication unexpectedly had no canonical change')
        bid,frame=result;entry['batch_id']=bid;return bid,frame
    finally:engine._people_staged=None


def verify_after_publish(engine,candidate,proof):
    from .face_decoration_support_alias_history import check
    store,entry=_entry(engine,proof['token']);owner,row,current,source=SCALAR._live(engine,candidate,entry['target'])
    if (engine._batch_controller() is not entry['batch'] or not entry['claimed'] or owner is not entry['owner']
            or row is not entry['row'] or engine._load_id!=entry['load_id']
            or engine._document_versions().workspace!=entry['workspace'] or owner.fence!=entry['fence']+1
            or candidate!=entry['candidate'] or proof!=_proof(entry['review']) or engine._people_support!=entry['assets']
            or source!=entry['review']['owner']['source_proof']):
        raise ValueError('Published support graph, bank or owner differs from the review')
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256'],advance=False)
    if len(members)!=len(entry['members']):raise ValueError('Published support alias membership changed')
    for actual,frozen in zip(members,entry['members']):
        other,own,source_proof,version=actual;visual=frozen['visual']
        if (other is not frozen['row'] or other['path']!=frozen['path'] or version.document_id!=visual['document_id']
                or version.revision!=int(visual['revision'])+1 or source_proof!=visual['source_proof']
                or snapshot_key(engine,other,own,candidate)!=frozen['after_key']):
            raise ValueError('Published support alias full member state differs from its reviewed candidate')
        SOURCE.verify_row({**other,'state':own},source_proof)
    expected=deepcopy(entry['targets'])
    for value in expected.values():value['revision']+=1
    receipt=entry['batch'].ledger.get(entry.get('batch_id'),{});marker=check(receipt)
    if (marker is None or marker['review_sha256']!=proof['history_review_sha256']
            or receipt.get('targets')!=entry['targets'] or CLOSURE._targets(engine,entry['batch'],_plans(entry),current)!=expected):
        raise ValueError('Support alias protected history or complete ledger closure was not retained exactly')


def status(engine,state,source,ref):
    out={'support_alias_review':None,'support_alias_reason':None}
    if ref is None:return out
    target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
    try:
        owner,row,current,proof=SCALAR._live(engine,state,target)
        CLOSURE.verify_dormant(engine,row,{source['sha256']});CLOSURE._eligible(engine,row,current,source['sha256'])
        PLAN.visibility(state,engine._people_support,ref)
        for entry in reversed(list(_store(engine)['pending'].values())):
            if not entry['claimed'] and entry['before']==state and entry['target']==target and entry['load_id']==engine._load_id:
                _verify(engine,state,target,entry);out['support_alias_review']=deepcopy(entry['review']);break
    except (ValueError,TypeError,KeyError,AttributeError,OSError) as error:out['support_alias_reason']=str(error)
    return out
