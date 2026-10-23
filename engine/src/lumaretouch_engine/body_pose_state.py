"""One stable BodyRef bank with operation-specific recipes/reviews/support.

Body identity and person links are shared. Visibility/support authorizations are
not shared between operations. Unknown operations remain visibly unapplied data.
"""
from copy import deepcopy
from . import body_pose_evidence as E,body_pose_operations as O


def empty():
    return {'version':2,'revision':0,'association_revision':0,'bodies':{},'analysis_runs':{},'support_assets':{}}


def migrate_v1(value):
    """The original shoulder-only schema migrates to one shoulder operation.

    No old shoulder review is widened to other anatomy. IDs/revisions/values are
    preserved; this structural migration is not new inference or user approval.
    """
    if type(value) is not dict or set(value)!={'version','revision','association_revision','bodies','analysis_runs'} or type(value['version']) is not int or value['version']!=1:raise ValueError('Unsupported old body bank')
    out=deepcopy(value);out['version']=2;out['support_assets']={}
    for row in out['bodies'].values():
        if type(row) is not dict or set(row)!={'record','enabled','recipe','review','association'}:raise ValueError('Malformed shoulder-only body row')
        review=row.pop('review')
        if review is not None:
            if type(review) is not dict or set(review)!={'body_ref','points_sha256','visible_anchors','ownership_confirmed','review_revision'}:raise ValueError('Malformed old shoulder review')
            review={**review,'operation_id':O.SHOULDER_OPERATION,'support_sha256':None}
        row['operations']={O.SHOULDER_OPERATION:{'enabled':True,'recipe':row.pop('recipe'),'review':review,'support_sha256':None}}
    return out


def check(value,*,operation_policies=None):
    if type(value) is dict and type(value.get('version')) is int and value['version']==1:value=migrate_v1(value)
    if type(value) is not dict or set(value)!=set(empty()) or type(value['version']) is not int or value['version']!=2:raise ValueError('Unsupported body bank')
    E.revision(value['revision']);E.revision(value['association_revision'])
    if type(value['bodies']) is not dict or len(value['bodies'])>4096:raise ValueError('Body bank exceeds budget')
    assets=value['support_assets']
    if type(assets) is not dict or len(assets)>4096:raise ValueError('Body support bank exceeds budget')
    asset_bytes=0
    for key,asset in assets.items():
        import json
        asset_bytes+=len(json.dumps(asset,separators=(',',':'),allow_nan=False).encode())
        if asset_bytes>24*1024*1024:raise ValueError('Retained body support assets exceed byte budget')
        E.digest(key);O.check_support_record(asset)
        if E.content_digest(asset)!=key:raise ValueError('Immutable body support asset changed')
    associations=set()
    for key,row in value['bodies'].items():
        if type(row) is not dict or set(row)!={'record','enabled','operations','association'}:raise ValueError('Invalid retained body row')
        record=E.check(row['record']);ref=record['body_ref']
        if key!=ref['body_instance_id'] or ref['analysis_revision']>value['revision'] or type(row['enabled']) is not bool:raise ValueError('Body identity/status mismatch')
        if type(row['operations']) is not dict or len(row['operations'])>O.MAX_OPERATIONS:raise ValueError('Body operation bank exceeds budget')
        for operation_id,item in row['operations'].items():O.check_operation(operation_id,item,record,assets,value['revision'],operation_policies=operation_policies)
        link=row['association']
        if link is not None:
            if type(link) is not dict or set(link)!={'person_id','body_ref','people_association_revision','confirmation_revision'} or E.ref(link['body_ref'])!=ref:raise ValueError('Body-person link requires distinct current BodyRef')
            E.token(link['person_id']);E.revision(link['people_association_revision']);E.revision(link['confirmation_revision'])
            if link['confirmation_revision']>value['association_revision']:raise ValueError('Future body association')
            pair=(ref['asset_sha256'],link['person_id'])
            if pair in associations:raise ValueError('Two bodies cannot silently claim one person in a photo')
            associations.add(pair)
    if type(value['analysis_runs']) is not dict or len(value['analysis_runs'])>4096:raise ValueError('Body analysis run budget exceeded')
    for asset,run in value['analysis_runs'].items():
        E.digest(asset)
        if type(run) is not dict or set(run)!={'detector_limit','limit_reached','census_complete'} or type(run['detector_limit']) is not int or not 1<=run['detector_limit']<=8 or type(run['limit_reached']) is not bool or run['census_complete'] is not False:raise ValueError('Invalid body detection budget evidence')
    return deepcopy(value)


def add_run(state,run,*,initial_operations=(O.SHOULDER_OPERATION,),operation_policies=None):
    out=check(state,operation_policies=operation_policies);source=E.source(run['source'])
    if len(set(initial_operations))!=len(initial_operations):raise ValueError('Duplicate initial body operation')
    if len(run['records'])>run['detector_limit']:raise ValueError('Pose producer exceeded declared budget')
    for record in run['records']:
        record=E.check(record);key=record['body_ref']['body_instance_id']
        if record['source']!=source or key in out['bodies']:raise ValueError('Fresh detection cannot replace/reidentify an existing body')
        out['bodies'][key]={'record':record,'enabled':True,'operations':{op:O.empty_operation(op,operation_policies=operation_policies) for op in initial_operations},'association':None}
    out['analysis_runs'][source['sha256']]={k:run[k] for k in ('detector_limit','limit_reached','census_complete')};out['revision']+=1
    return check(out,operation_policies=operation_policies)


def target(state,body_ref):
    ref=E.ref(body_ref);row=state['bodies'].get(ref['body_instance_id'])
    if row is None or row['record']['body_ref']!=ref:raise ValueError('Body target changed; do not use list position or nearest face')
    return row


def operation(state,body_ref,operation_id=O.SHOULDER_OPERATION):
    E.token(operation_id);item=target(state,body_ref)['operations'].get(operation_id)
    if item is None:raise ValueError('Body has no retained intent for operation: '+operation_id)
    return item


def _ensure_operation(row,operation_id,operation_policies):
    O.require_policy(operation_id,operation_policies)
    return row['operations'].setdefault(operation_id,O.empty_operation(operation_id,operation_policies=operation_policies))


def set_support(state,body_ref,operation_id,kind,data,*,operation_policies=None):
    out=check(state,operation_policies=operation_policies);row=target(out,body_ref)
    item=_ensure_operation(row,operation_id,operation_policies)
    support=O.support_record(operation_id,row['record'],kind,data,operation_policies=operation_policies);key=E.content_digest(support)
    if key in out['support_assets'] and out['support_assets'][key]!=support:raise ValueError('Body support asset hash collision')
    out['support_assets'][key]=support
    if item['support_sha256']!=key:item['support_sha256']=key;item['review']=None;out['revision']+=1
    return check(out,operation_policies=operation_policies)


def support(state,body_ref,operation_id):
    item=operation(state,body_ref,operation_id);key=item['support_sha256']
    if key is None:return None
    value=state['support_assets'].get(key);record=target(state,body_ref)['record']
    if value is None or E.content_digest(value)!=key or value['operation_id']!=operation_id or value['body_ref']!=body_ref or value['points_sha256']!=record['points_sha256'] or value['source']!=record['source']:raise ValueError('Body operation support lost exact ownership')
    return deepcopy(value)


def review(state,body_ref,*,points_sha256,visible_anchors,ownership_confirmed,operation_id=O.SHOULDER_OPERATION,support_sha256=None,operation_policies=None):
    out=check(state,operation_policies=operation_policies);row=target(out,body_ref);policy=O.require_policy(operation_id,operation_policies);item=_ensure_operation(row,operation_id,operation_policies)
    if visible_anchors!=list(policy.required_anchors) or ownership_confirmed is not True or points_sha256!=row['record']['points_sha256'] or support_sha256!=item['support_sha256']:raise ValueError('Review must name this operation’s exact anchors, observed support and ownership')
    if policy.support_kind is not None and support(out,body_ref,operation_id) is None:raise ValueError('This operation needs separately reviewed visible source support')
    for index in policy.required_anchors:
        p=row['record']['points'][index]
        if p['visibility']<policy.min_visibility or p['presence']<policy.min_presence or not (0<p['x']<1 and 0<p['y']<1):raise ValueError('An operation anchor remains unverifiable; never invent hidden anatomy')
    out['revision']+=1
    item['review']={'operation_id':operation_id,'body_ref':E.ref(body_ref),'points_sha256':points_sha256,'visible_anchors':list(policy.required_anchors),'ownership_confirmed':True,'review_revision':out['revision'],'support_sha256':support_sha256}
    return check(out,operation_policies=operation_policies)


def associate(state,body_ref,person_id,people_state,*,user_confirmed):
    from .people_state import check as check_people
    out=check(state);row=target(out,body_ref);people=check_people(people_state)
    if user_confirmed is not True or person_id not in people['persons']:raise ValueError('Select and confirm an existing anonymous person explicitly')
    out['revision']+=1;out['association_revision']+=1
    row['association']={'person_id':person_id,'body_ref':E.ref(body_ref),'people_association_revision':people['association_revision'],'confirmation_revision':out['association_revision']}
    return check(out)


def unlink(state,body_ref):
    out=check(state);target(out,body_ref)['association']=None;out['revision']+=1;out['association_revision']+=1
    return check(out)


def set_recipe(state,body_ref,value,*,operation_id=O.SHOULDER_OPERATION,operation_policies=None):
    out=check(state,operation_policies=operation_policies);row=target(out,body_ref);policy=O.require_policy(operation_id,operation_policies);created=operation_id not in row['operations'];item=_ensure_operation(row,operation_id,operation_policies);value=policy.check_recipe(value)
    if item['recipe']==value and not created:return check(out,operation_policies=operation_policies)
    item['recipe']=value;out['revision']+=1
    return check(out,operation_policies=operation_policies)


def set_operation_enabled(state,body_ref,operation_id,enabled,*,operation_policies=None):
    out=check(state,operation_policies=operation_policies)
    if type(enabled) is not bool:raise ValueError('Operation enabled status must be explicit')
    item=operation(out,body_ref,operation_id)
    if item['enabled']!=enabled:item['enabled']=enabled;out['revision']+=1
    return check(out,operation_policies=operation_policies)


def reanalyse(state,body_ref,measured,*,user_confirmed):
    out=check(state);row=target(out,body_ref)
    row['record']=E.explicit_reanalysis(row['record'],measured,expected_ref=body_ref,user_confirmed=user_confirmed)
    # Bank revision survives undo. A later analysis must not reuse a historical
    # BodyRef analysis revision after undoing an earlier reanalysis.
    row['record']['body_ref']['analysis_revision']=out['revision']+1
    for item in row['operations'].values():item['review']=None;item['support_sha256']=None
    row['association']=None;out['revision']+=1;out['association_revision']+=1
    # Portable recipes survive. Old source supports remain in immutable assets for
    # history, but no active pointer/review is rebound to a new pose observation.
    return check(out)
