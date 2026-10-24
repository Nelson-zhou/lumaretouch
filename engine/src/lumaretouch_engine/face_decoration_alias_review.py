# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete direct scalar edit of one shared-source face; no support copying."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json,time,uuid,re
from . import people_state as S, people_algorithms as A, people_resolver as R
from . import face_decoration_state as D, virtual_copy_people as V, creative_derived_source as SOURCE
from . import face_style_alias_review as CLOSURE, people_batch_ledger as LEDGER
from . import collarbone_transfer_review as VISUAL
from .portrait_review_render import image as render_image,snapshot_key

READS=frozenset(('face_decoration_alias_preview','face_decoration_alias_image'))
ACTIONS=READS|{'face_decoration_alias_confirm'}
TTL=1800
MAX_REVIEWS=4


def digest(v):return sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def check_action(action,payload,target):
    if action not in ACTIONS or type(payload) is not dict or type(target) is not dict or set(target)!={'scope','target_id','face_ref'} or target['scope']!='face':
        raise ValueError('Decoration aliases require one explicitly selected retained face')
    ref=S.check_ref(target['face_ref'])
    if ref['face_instance_id']!=target['target_id']:raise ValueError('Decoration alias target differs from FaceRef')
    if action=='face_decoration_alias_preview':
        if set(payload)!={'recipe'} or type(payload['recipe']) is not dict:raise ValueError('Alias edit transfers only the original versioned pattern and strength')
        D.check(payload['recipe'])
    else:
        if type(payload.get('token')) is not str or re.fullmatch('[0-9a-f]{32}',payload['token']) is None:raise ValueError('Exact decoration alias review token required')
        if action=='face_decoration_alias_image':
            if set(payload)!={'token','document_id','side','sha256'} or payload['side'] not in ('before','after'):raise ValueError('Exact alias image coordinates required')
            S.token(payload['document_id']);S.digest(payload['sha256'])
        else:
            if set(payload)!={'token','ack'}:raise ValueError('Exact complete alias acknowledgment required')
            CLOSURE.check_ack(payload['ack'])


def _store(engine):
    store=engine.__dict__.get('_face_decoration_alias_reviews')
    if store is None:
        from .collarbone_visual_store import _Images
        store={'pending':OrderedDict(),'images':_Images(records=lambda p:p.records)}
        engine._face_decoration_alias_reviews=store
    for token,entry in list(store['pending'].items()):
        if time.monotonic()>=entry['expires']:del store['pending'][token]
    store['images'].prune({key:entry for key,entry in store['pending'].items() if not entry['claimed']})
    return store


def _entry(engine,token):
    store=_store(engine);entry=store['pending'].get(token)
    if entry is None:raise ValueError('Decoration alias review expired; prepare and inspect every image again')
    return store,entry


def _live(engine,state,target):
    from .people_preset_plan import require_active_owner
    owner=require_active_owner(engine);row=V.current_row(engine)
    if row is None or V.scope(row)!='project' or owner.snapshot()!=state:raise ValueError('Decoration aliases require their exact shared project owner')
    ref=S.check_ref(target['face_ref']);face=state['faces'].get(target['target_id'])
    if face is None or not face['enabled'] or S.face_ref(face)!=ref:raise ValueError('Decoration alias face changed')
    current=engine._people_preset_capture();source=SOURCE.row_proof({**row,'state':current})
    if ref['asset_sha256']!=source['asset_sha256'] or engine._people_cursors.get(source['asset_sha256'])!=target['target_id'] or engine._people_targets.get(source['asset_sha256'])!=target:
        raise ValueError('Decoration aliases need the explicit current effective-source face')
    return owner,row,current,source


def _plans(entry):
    return {'project':{'row':entry['row'],'before':entry['before'],'candidate':entry['candidate'],'reviewed_face_refs':deepcopy(entry['refs'])}}


def _plan(review):return SimpleNamespace(token=review['token'],records={m['visual']['document_id']:m['visual'] for m in review['members']})


def _ack(review):
    return {'review_sha256':review['review_sha256'],'members':[{'document_id':v['document_id'],'revision':v['revision'],'before_sha256':v['before']['sha256'],'after_sha256':v['after']['sha256']} for v in (m['visual'] for m in review['members'])]}


def _proof(review):
    return {'kind':'face_decoration_alias_confirm','token':review['token'],'review_sha256':review['review_sha256'],'recipe':deepcopy(review['recipe']),
        'candidate_state_revision':review['candidate_state_revision'],'ack':_ack(review),'history_review_sha256':digest(_ack(review)),
        'alias_members':[{'document_id':m['visual']['document_id'],'expected_revision':m['visual']['revision'],'result_revision':str(int(m['visual']['revision'])+1)} for m in review['members']]}


def _coverage(engine,row,recipe,before,candidate,ref):
    from .face_decoration_batch_plan import coverage
    return coverage(engine,{**row,'state':recipe},before,candidate,{'target_refs':[ref]})


def _verify(engine,state,target,entry):
    owner,row,current,source=_live(engine,state,target);review=entry['review']
    if engine._batch_controller() is not entry['batch'] or entry['claimed'] or owner is not entry['owner'] or owner.fence!=entry['fence'] or row is not entry['row'] or engine._load_id!=entry['load_id'] or state!=entry['before'] or target!=entry['target'] or source!=review['owner']['source_proof'] or engine._document_versions().workspace!=entry['workspace']:
        raise ValueError('Decoration alias owner/source/graph/session changed')
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256'])
    if len(members)!=len(entry['members']):raise ValueError('Decoration alias membership changed')
    for actual,frozen in zip(members,entry['members']):
        other,recipe,proof,version=actual;visual=frozen['visual']
        if (other is not frozen['row'] or other['path']!=frozen['path'] or version.document_id!=visual['document_id'] or str(version.revision)!=visual['revision'] or proof!=visual['source_proof']
                or snapshot_key(engine,other,recipe,state)!=frozen['before_key'] or snapshot_key(engine,other,recipe,entry['candidate'])!=frozen['after_key']
                or _coverage(engine,other,recipe,state,entry['candidate'],target['face_ref'])!=frozen['coverage']):
            raise ValueError('Decoration alias crop/repair/support/recipe or source proof changed')
        SOURCE.verify_row({**other,'state':recipe},proof)
    if CLOSURE._targets(engine,entry['batch'],_plans(entry),current)!=entry['targets']:raise ValueError('Decoration alias ledger closure changed')
    return current


def preview(engine,state,target,payload):
    from .people_edit import stage
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    from .people_transfer_inventory import proof
    check_action('face_decoration_alias_preview',payload,target)
    owner,row,current,source=_live(engine,state,target);recipe=D.check(payload['recipe'])
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    binding=engine._people_binding()
    command={**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},'state_revision':state['revision'],'association_revision':state['association_revision'],'request_id':uuid.uuid4().hex,'target':target,'action':'patch','payload':{'patches':D.patches(recipe)}}
    size=SOURCE.binding(current,row['path'],(row['src_w'],row['src_h']))
    candidate=stage(command,state,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},asset_sha256=source['asset_sha256'],source_dimensions=(size['width'],size['height']))['state']
    if not between(state,candidate):raise ValueError('Decoration recipe already matches; no alias transaction or review was created')
    if candidate['revision']>CLOSURE.MAX_REVISION or affected_assets(state,candidate)!={source['asset_sha256']}:raise ValueError('Decoration alias patch changed another source or exceeded exact revision budget')
    A.validate_compatibility(A.recipes(R.resolve(candidate,target['target_id'],A.defaults())))
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256']);batch=engine._batch_controller()
    coverage=_coverage(engine,row,current,state,candidate,target['face_ref'])
    refs=[item['face_ref'] for item in coverage['targets']]
    entry={'owner':owner,'row':row,'fence':owner.fence,'load_id':engine._load_id,'workspace':engine._document_versions().workspace,'batch':batch,'target':deepcopy(target),'before':deepcopy(state),'candidate':candidate,'refs':refs,'members':[],'claimed':False}
    targets=CLOSURE._targets(engine,batch,_plans(entry),current)
    if {t['document_id'] for t in targets.values()}!={m[3].document_id for m in members} or len(targets)!=len(members):raise ValueError('Decoration alias ledger omits or adds affected documents')
    entry['targets']=deepcopy(targets);public=[];displays={}
    for other,own,source_proof,version in members:
        cov=_coverage(engine,other,own,state,candidate,target['face_ref'])
        before_key=snapshot_key(engine,other,own,state);after_key=snapshot_key(engine,other,own,candidate)
        a,left,pa=render_image(engine,other,own,state,version.document_id,str(version.revision))
        b,right,pb=render_image(engine,other,own,candidate,version.document_id,str(version.revision))
        if pa['source_proof']!=source_proof or pb['source_proof']!=source_proof or pa['source_size']!=pb['source_size']:raise ValueError('Decoration alias pair changed immutable source')
        visual=VISUAL.checked({'version':1,'document_id':version.document_id,'revision':str(version.revision),'source_proof':source_proof,'before_state_sha256':pa['candidate_sha256'],'candidate_state_sha256':pb['candidate_sha256'],'before_people_sha256':pa['people_sha256'],'candidate_people_sha256':pb['people_sha256'],'source_size':pa['source_size'],'before_output_size':pa['output_size'],'after_output_size':pb['output_size'],'coverage_sha256':VISUAL.coverage_digest(cov),'before':a,'after':b})
        public.append({'path':other['path'],'coverage':cov,'visual':visual})
        entry['members'].append({'row':other,'path':other['path'],'coverage':cov,'visual':visual,'before_key':before_key,'after_key':after_key})
        displays[version.document_id]={'revision':str(version.revision),'before':left,'after':right}
    token=uuid.uuid4().hex
    review={'version':1,'token':token,'recipe':recipe,'owner':proof(engine,row,state,source_row={**row,'state':current}),'face_ref':deepcopy(target['face_ref']),'candidate_state_revision':candidate['revision'],'members':public}
    review['review_sha256']=digest(review);entry.update(review=review,expires=time.monotonic()+TTL)
    _verify(engine,state,target,entry);store=_store(engine)
    while len(store['pending'])>=MAX_REVIEWS:store['pending'].popitem(last=False)
    store['images'].prune(store['pending']);store['images'].attach(_plan(review),displays);store['pending'][token]=entry
    return {'kind':'face_decoration_alias_preview','review':deepcopy(review)}


def image(engine,state,target,payload):
    check_action('face_decoration_alias_image',payload,target);store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    review=entry['review'];visual=_plan(review).records.get(payload['document_id'])
    if visual is None or visual[payload['side']]['sha256']!=payload['sha256']:raise ValueError('Image is not a frozen decoration alias member')
    pixels=store['images'].read(_plan(review),payload['document_id'],visual['revision'],payload['side'],payload['sha256']);_verify(engine,state,target,entry)
    return {'kind':'face_decoration_alias_image',**deepcopy(payload),'review_sha256':review['review_sha256'],'image':pixels}


def confirm(engine,state,target,payload):
    check_action('face_decoration_alias_confirm',payload,target);store,entry=_entry(engine,payload['token']);_verify(engine,state,target,entry)
    if payload['ack']!=_ack(entry['review']):raise ValueError('Review and acknowledge every decoration alias image in exact order')
    _available(store,entry['review']);return deepcopy(entry['candidate']),_proof(entry['review'])


def _available(store,review):
    plan=_plan(review)
    for v in plan.records.values():
        for side in ('before','after'):store['images'].read(plan,v['document_id'],v['revision'],side,v[side]['sha256'])


def publish(engine,state,target,payload,candidate,proof,request_id,mark_started=lambda:None):
    from .face_decoration_alias_history import prepare
    from .face_decoration_alias_authority import mint
    store,entry=_entry(engine,payload['token']);current=_verify(engine,state,target,entry)
    if candidate!=entry['candidate'] or proof!=_proof(entry['review']) or payload['ack']!=proof['ack']:raise ValueError('Decoration alias publication differs from exact reviewed graph')
    plans=_plans(entry);targets=deepcopy(entry['targets']);batch=entry['batch']
    batch.documents.remember_current()
    _verify(engine,state,target,entry)
    history=prepare(engine,plans,targets,payload['ack'])
    plans['project']['decoration_alias_authority']=mint(engine,entry['row'],state,candidate,targets,entry['refs'])
    try:
        LEDGER.prepare_scoped(engine,plans,targets);LEDGER._verify(batch,engine,plans,targets)
        _verify(engine,state,target,entry);_available(store,entry['review'])
        if LEDGER._targets(batch,engine,plans)!=targets:raise ValueError('Decoration alias ledger changed before token claim')
        mark_started();entry['claimed']=True
        result=LEDGER.commit_scoped(batch,engine,plans,request_id=request_id,prepare=False,prepared_targets=targets,face_decoration_alias_history=history)
        if result is None:raise ValueError('Decoration alias publication unexpectedly had no canonical change')
        bid,frame=result;entry['batch_id']=bid;return bid,frame
    finally:engine._people_staged=None


def verify_after_publish(engine,candidate,proof):
    from .face_decoration_alias_history import check
    store,entry=_entry(engine,proof['token']);owner,row,current,source=_live(engine,candidate,entry['target'])
    if (engine._batch_controller() is not entry['batch'] or not entry['claimed'] or owner is not entry['owner'] or row is not entry['row']
            or engine._load_id!=entry['load_id'] or engine._document_versions().workspace!=entry['workspace']
            or owner.fence!=entry['fence']+1 or candidate!=entry['candidate'] or proof!=_proof(entry['review'])
            or source!=entry['review']['owner']['source_proof']):raise ValueError('Decoration alias published graph/fence differs from review')
    CLOSURE.verify_dormant(engine,row,{source['asset_sha256']})
    members=CLOSURE._eligible(engine,row,current,source['asset_sha256'],advance=False)
    if len(members)!=len(entry['members']):raise ValueError('Published decoration alias membership changed')
    for actual,frozen in zip(members,entry['members']):
        other,own,source_proof,version=actual;visual=frozen['visual']
        if other is not frozen['row'] or other['path']!=frozen['path'] or version.document_id!=visual['document_id'] or version.revision!=int(visual['revision'])+1 or source_proof!=visual['source_proof'] or snapshot_key(engine,other,own,candidate)!=frozen['after_key']:
            raise ValueError('Published decoration alias full state differs from reviewed candidate')
        SOURCE.verify_row({**other,'state':own},source_proof)
    marker=check(entry['batch'].ledger[entry['batch_id']])
    if marker is None or marker['review_sha256']!=proof['history_review_sha256']:raise ValueError('Decoration alias protected history was not retained exactly')


def status(engine,state,source,ref):
    out={'alias_required':False,'alias_member_count':0,'alias_reason':None,'alias_review':None}
    if ref is None:return out
    target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
    try:
        owner,row,current,proof=_live(engine,state,target)
        rows=[other for other in CLOSURE._scope_rows(engine,row) if SOURCE.row_asset(CLOSURE._source_row(engine,other,current))==source['sha256']]
        out.update(alias_required=len(rows)>1,alias_member_count=len(rows))
        if len(rows)>1:
            CLOSURE.verify_dormant(engine,row,{source['sha256']});CLOSURE._eligible(engine,row,current,source['sha256'])
        for entry in reversed(list(_store(engine)['pending'].values())):
            if not entry['claimed'] and entry['before']==state and entry['target']==target and entry['load_id']==engine._load_id:
                out['alias_review']=deepcopy(entry['review']);break
    except (ValueError,TypeError,KeyError,AttributeError,OSError) as error:out['alias_reason']=str(error)
    return out
