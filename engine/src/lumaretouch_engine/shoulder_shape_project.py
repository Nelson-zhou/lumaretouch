"""Durable operation-owned body bank, protected history and export snapshots.

The shared project container is v13, so older readers reject rather than
silently drop body operations. v12 semantic colour/v11 sky remain migratable.
Derived fields are never serialized.
"""
from copy import deepcopy
import json
from . import body_pose_state as B,body_pose_evidence as E,body_pose_operations as O
from .body_pose_geometry import DEFAULT_BODY_ORDER


def pack(state,*,operation_policies=None):
    state=B.check(state,operation_policies=operation_policies)
    if len(json.dumps(state,separators=(',',':'),allow_nan=False).encode())>32*1024*1024:raise ValueError('Body bank exceeds project byte budget')
    return {'version':2,'state':state,'content_sha256':E.content_digest(state)}


def unpack(value,*,operation_policies=None):
    if type(value) is not dict or set(value)!={'version','state','content_sha256'} or type(value['version']) is not int or value['version'] not in (1,2):raise ValueError('Invalid retained body project data')
    E.digest(value['content_sha256'])
    if E.content_digest(value['state'])!=value['content_sha256']:raise ValueError('Retained body project digest changed')
    if value['version']==1 and value['state'].get('version')!=1:raise ValueError('Old body envelope must contain the old shoulder-only bank')
    if value['version']==2 and value['state'].get('version')!=2:raise ValueError('Operation-owned body envelope needs bank v2')
    state=B.check(value['state'],operation_policies=operation_policies)
    pack(state,operation_policies=operation_policies)  # byte budget after checked migration
    return state


def snapshot(state,source,*,operation_policies=None,body_operation_order=DEFAULT_BODY_ORDER):
    state=B.check(state,operation_policies=operation_policies);source=E.source(source)
    rows={k:row for k,row in state['bodies'].items() if row['record']['source']==source}
    same_asset=[row for row in state['bodies'].values() if row['record']['source']['sha256']==source['sha256']]
    if len(rows)!=len(same_asset):raise ValueError('Same source digest has conflicting orientation/dimensions')
    return {'version':2,'source':source,'bank':pack(state,operation_policies=operation_policies),'body_refs':[deepcopy(row['record']['body_ref']) for _,row in sorted(rows.items())],'body_operation_order':body_operation_order.record()}


def check_snapshot(value,source,*,operation_policies=None,body_operation_order=DEFAULT_BODY_ORDER):
    keys={'version','source','bank','body_refs','body_operation_order'}
    if type(value) is not dict or set(value)!=keys or value['version']!=2 or E.source(source)!=value['source']:raise ValueError('Body export source/version changed')
    if value['body_operation_order']!=body_operation_order.record():raise ValueError('Frozen body operation order differs from export snapshot')
    state=unpack(value['bank'],operation_policies=operation_policies)
    if snapshot(state,source,operation_policies=operation_policies,body_operation_order=body_operation_order)!=value:raise ValueError('Body export snapshot ownership changed')
    return state


def history_patch(before,after):
    a=B.check(before);b=B.check(after)
    if any(b['support_assets'].get(key)!=asset for key,asset in a['support_assets'].items()):raise ValueError('Body support assets are append-only across edits')
    keys=set(a['bodies'])|set(b['bodies'])
    changed={key:{'before':deepcopy(a['bodies'].get(key)),'after':deepcopy(b['bodies'].get(key))} for key in keys if a['bodies'].get(key)!=b['bodies'].get(key)}
    needed={item['support_sha256'] for change in changed.values() for row in change.values() if row is not None for item in row['operations'].values() if item['support_sha256'] is not None}
    return {'version':2,'changes':changed,'before_association_revision':a['association_revision'],'after_association_revision':b['association_revision'],'analysis_runs_before':deepcopy(a['analysis_runs']),'analysis_runs_after':deepcopy(b['analysis_runs']),'support_assets':{key:deepcopy(b['support_assets'][key]) for key in needed}}


def replay_patch(current,patch,*,undo,expected_association_revision):
    out=B.check(current)
    keys={'version','changes','before_association_revision','after_association_revision','analysis_runs_before','analysis_runs_after','support_assets'}
    if type(patch) is not dict or set(patch)!=keys or type(patch['version']) is not int or patch['version']!=2 or type(undo) is not bool or out['association_revision']!=expected_association_revision:raise ValueError('Body history schema/association changed; explicit review required')
    before,after=('after','before') if undo else ('before','after')
    for key,change in patch['changes'].items():
        if set(change)!={'before','after'} or out['bodies'].get(key)!=change[before]:raise ValueError('Body history would overwrite a later edit or changed analysis')
    if out['analysis_runs']!=patch['analysis_runs_'+before]:raise ValueError('Body analysis changed since this history entry')
    for key,asset in patch['support_assets'].items():
        E.digest(key);O.check_support_record(asset)
        if E.content_digest(asset)!=key or (key in out['support_assets'] and out['support_assets'][key]!=asset):raise ValueError('Immutable body history support changed')
        out['support_assets'][key]=deepcopy(asset)
    for key,change in patch['changes'].items():
        if change[after] is None:out['bodies'].pop(key,None)
        else:out['bodies'][key]=deepcopy(change[after])
    out['analysis_runs']=deepcopy(patch['analysis_runs_'+after]);out['revision']+=1
    if patch['before_association_revision']!=patch['after_association_revision']:out['association_revision']+=1
    return B.check(out)


def transfer_recipe(source_state,source_ref,target_state,target_ref,*,confirmed_person_id,people_association_revision,operation_id=O.SHOULDER_OPERATION,operation_policies=None):
    """Copy only the named operation's values; target keeps its own reviewed support.

    Caller must PREPARE the actual target before publication. Both current links
    name the same reviewed anonymous person and graph fence. No pose, visibility
    authorization, contour, source geometry or stable ID crosses photographs.
    """
    a=B.check(source_state,operation_policies=operation_policies);b=B.check(target_state,operation_policies=operation_policies)
    src=B.target(a,source_ref);dst=B.target(b,target_ref);policy=O.require_policy(operation_id,operation_policies)
    E.token(confirmed_person_id);E.revision(people_association_revision)
    if not src['enabled'] or not dst['enabled']:raise ValueError('Body transfer requires enabled source and target bodies')
    for row in (src,dst):
        link=row['association']
        if link is None or link['person_id']!=confirmed_person_id or link['people_association_revision']!=people_association_revision:raise ValueError('Body transfer requires current explicitly confirmed person ownership on both bodies')
    source_item=B.operation(a,source_ref,operation_id);target_item=B.operation(b,target_ref,operation_id)
    if not source_item['enabled'] or not target_item['enabled'] or target_item['review'] is None:raise ValueError('Target operation must have its own visible support review and be enabled')
    return B.set_recipe(b,target_ref,policy.check_recipe(deepcopy(source_item['recipe'])),operation_id=operation_id,operation_policies=operation_policies)
