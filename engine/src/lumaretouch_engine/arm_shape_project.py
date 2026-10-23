# SPDX-License-Identifier: GPL-3.0-or-later
"""Family-scoped shared-bank history, source-owned assets and intent transfer."""
from copy import deepcopy
from . import arm_shape_state as S, body_pose_state as B, body_pose_evidence as E
from . import shoulder_shape_project as Common
from .body_pose_geometry import PORTRAIT_BODY_ORDER, effective_order as common_effective_order
BODY_ORDER=PORTRAIT_BODY_ORDER


def check(state,*,operation_policies=None):return B.check(state,operation_policies={**(operation_policies or {}),**S.policies()})
def pack(state):return Common.pack(check(state),operation_policies=S.policies())
def unpack(value):return check(Common.unpack(value,operation_policies=S.policies()))
def effective_order(state):return common_effective_order(check(state))
def snapshot(state,source,*,body_operation_order=None):
    state=check(state)
    return Common.snapshot(state,source,operation_policies=S.policies(),body_operation_order=effective_order(state) if body_operation_order is None else body_operation_order)
def check_snapshot(value,source,*,body_operation_order=None):
    if type(value) is not dict or set(value)!={'version','source','bank','body_refs','body_operation_order'}:raise ValueError('Invalid frozen registered body snapshot')
    state=unpack(value['bank'])
    return check(Common.check_snapshot(value,source,operation_policies=S.policies(),body_operation_order=effective_order(state) if body_operation_order is None else body_operation_order))
def graph_digest(state):return E.content_digest(check(state))


def people_digest(state):
    from .people_state import check as check_people
    return E.content_digest(check_people(state))


def _protected(state):
    out=deepcopy(state);out.pop('revision');out.pop('support_assets')
    for row in out['bodies'].values():
        for operation_id in S.OPERATION_IDS.values():row['operations'].pop(operation_id,None)
    return out


def history_patch(before,after,*,people_sha256):
    a=check(before);b=check(after);E.digest(people_sha256)
    if _protected(a)!=_protected(b) or any(b['support_assets'].get(k)!=v for k,v in a['support_assets'].items()):
        raise ValueError('Arm edit changed another operation, observation, association or immutable support')
    changes=[]
    for key,row in a['bodies'].items():
        for operation_id in S.OPERATION_IDS.values():
            old=row['operations'].get(operation_id);new=b['bodies'][key]['operations'].get(operation_id)
            if old!=new:changes.append({'body_ref':row['record']['body_ref'],'operation_id':operation_id,'before':old,'after':new})
    needed={item['support_sha256'] for c in changes for item in (c['before'],c['after']) if item is not None and item['support_sha256'] is not None}
    payload={'version':1,'family_id':S.FAMILY_ID,'changes':deepcopy(changes),'people_sha256':people_sha256,
             'protected_graph_sha256':E.content_digest(_protected(a)),
             'support_assets':{key:deepcopy(b['support_assets'][key]) for key in needed}}
    return {**payload,'content_sha256':E.content_digest(payload)}


def replay_patch(current,patch,*,undo,people_state,expected_bank_sha256):
    out=check(current)
    if graph_digest(out)!=E.digest(expected_bank_sha256):raise ValueError('Arm history graph fence changed')
    keys={'version','family_id','changes','people_sha256','protected_graph_sha256','support_assets','content_sha256'}
    if type(undo) is not bool or type(patch) is not dict or set(patch)!=keys or patch['version']!=1 or patch['family_id']!=S.FAMILY_ID or E.content_digest({k:v for k,v in patch.items() if k!='content_sha256'})!=patch['content_sha256']:
        raise ValueError('Invalid retained arm history patch')
    if people_digest(people_state)!=patch['people_sha256'] or E.content_digest(_protected(out))!=patch['protected_graph_sha256']:
        raise ValueError('Arm history cannot reidentify people or overwrite unrelated later edits')
    old,new=('after','before') if undo else ('before','after');seen=set()
    for c in patch['changes']:
        if type(c) is not dict or set(c)!={'body_ref','operation_id','before','after'} or c['operation_id'] not in S.OPERATION_IDS.values():raise ValueError('Arm history contains another family')
        key=(E.content_digest(c['body_ref']),c['operation_id'])
        if key in seen:raise ValueError('Duplicate arm history mutation')
        seen.add(key);row=B.target(out,c['body_ref'])
        if row['operations'].get(c['operation_id'])!=c[old]:raise ValueError('Arm history would overwrite a later segment edit')
    for key,asset in patch['support_assets'].items():
        if key in out['support_assets'] and out['support_assets'][key]!=asset:raise ValueError('Immutable source-owned support changed')
        out['support_assets'][key]=deepcopy(asset)
    for c in patch['changes']:
        operations=B.target(out,c['body_ref'])['operations']
        if c[new] is None:operations.pop(c['operation_id'],None)
        else:operations[c['operation_id']]=deepcopy(c[new])
    out['revision']+=1
    return check(out)


def transfer_recipe(source_state,source_ref,target_state,target_ref,*,segments,people_state,
                    expected_people_sha256,expected_source_bank_sha256,expected_target_bank_sha256,
                    confirmed_person_id,user_confirmed):
    """Intent only. Target must have matching strategy evidence, review and person.

    The caller prepares the ENTIRE returned candidate before atomic publication.
    It must not skip an unavailable target segment or copy source support assets.
    """
    from .people_state import check as check_people
    people=check_people(people_state);a=check(source_state);b=check(target_state)
    if user_confirmed is not True or people_digest(people)!=E.digest(expected_people_sha256) or graph_digest(a)!=E.digest(expected_source_bank_sha256) or graph_digest(b)!=E.digest(expected_target_bank_sha256):
        raise ValueError('Arm transfer needs exact current people/source/target graph confirmation')
    if type(segments) is not list or not segments or len(set(segments))!=len(segments) or any(k not in S.SEGMENTS for k in segments):raise ValueError('Name the actual arm sides/segments to transfer')
    if confirmed_person_id not in people['persons']:raise ValueError('Confirmed person no longer exists')
    src=B.target(a,source_ref);dst=B.target(b,target_ref)
    for row in (src,dst):
        link=row['association'];ref=row['record']['body_ref']
        if not row['enabled'] or link is None or link['person_id']!=confirmed_person_id or link['people_association_revision']!=people['association_revision']:raise ValueError('Arm transfer requires explicit current person ownership on both photos')
        faces=[x for x in people['links'] if x['state']=='confirmed' and x['person_id']==confirmed_person_id and people['faces'][x['face_instance_id']]['asset_sha256']==ref['asset_sha256']]
        if len(faces)!=1:raise ValueError('Transfer requires one confirmed source face in each photograph')
    for key in segments:
        op=S.OPERATION_IDS[key];item=B.operation(a,source_ref,op);target=B.operation(b,target_ref,op)
        if not item['enabled'] or not target['enabled'] or target['review'] is None:raise ValueError('Each target segment needs its own reviewed visible contour')
        support=B.support(b,target_ref,op)
        if support is None or S.check_support(support['data'],dst['record'],segment=key)['strategy']!=item['recipe']['strategy']:raise ValueError('Target lacks independently reviewed evidence for this actual arm strategy')
        b=B.set_recipe(b,target_ref,S.check(item['recipe']),operation_id=op,operation_policies=S.policies())
    return b
