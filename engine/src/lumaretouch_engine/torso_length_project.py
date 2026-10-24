# SPDX-License-Identifier: GPL-3.0-or-later
"""Torso length hooks on the shared body bank: immutable support, guarded undo/transfer."""
from copy import deepcopy
from . import body_pose_state as B, body_pose_evidence as E, torso_length_state as S
from . import shoulder_shape_project as P
from .body_pose_geometry import TORSO_LENGTH_BODY_ORDER, effective_order as common_effective_order

BODY_ORDER = TORSO_LENGTH_BODY_ORDER


def check(state):
    return B.check(state,operation_policies=S.policies())


def pack(state):
    return P.pack(check(state),operation_policies=S.policies())


def unpack(value):
    return check(P.unpack(value,operation_policies=S.policies()))


def effective_order(state):
    """Compatibility port to the sole registered body ordering authority."""
    return common_effective_order(check(state))


def snapshot(state,source):
    state=check(state)
    return P.snapshot(state,source,operation_policies=S.policies(),body_operation_order=effective_order(state))


def check_snapshot(value,source):
    if type(value) is not dict or set(value)!={'version','source','bank','body_refs','body_operation_order'}:
        raise ValueError('Invalid frozen torso/body snapshot')
    state=unpack(value['bank'])
    return check(P.check_snapshot(value,source,operation_policies=S.policies(),body_operation_order=effective_order(state)))


def graph_digest(state):
    """Exact live graph fence; do not authorize from an association counter only."""
    return E.content_digest(check(state))


def people_digest(people_state):
    from .people_state import check as check_people
    return E.content_digest(check_people(people_state))


def history_patch(before,after,*,people_sha256):
    a=check(before); b=check(after); E.digest(people_sha256)
    # Only this operation may change here. Preserve all other body operations,
    # identity, associations, analysis data and append-only support objects.
    expected=deepcopy(a)
    for key,row in a['bodies'].items():
        if key not in b['bodies']: raise ValueError('Torso length history cannot delete a body')
        torso=b['bodies'][key]['operations'].get(S.OPERATION_ID)
        if torso is None: expected['bodies'][key]['operations'].pop(S.OPERATION_ID,None)
        else: expected['bodies'][key]['operations'][S.OPERATION_ID]=deepcopy(torso)
    expected['revision']=b['revision']; expected['support_assets']=deepcopy(b['support_assets'])
    if expected!=b or any(b['support_assets'].get(k)!=v for k,v in a['support_assets'].items()):
        raise ValueError('Torso length edit tried to mutate unrelated graph state or an immutable support asset')
    changes={k:{'body_ref':deepcopy(row['record']['body_ref']),
                'before':deepcopy(row['operations'].get(S.OPERATION_ID)),
                'after':deepcopy(b['bodies'][k]['operations'].get(S.OPERATION_ID))}
             for k,row in a['bodies'].items()
             if row['operations'].get(S.OPERATION_ID)!=b['bodies'][k]['operations'].get(S.OPERATION_ID)}
    protected=deepcopy(a)
    protected.pop('revision'); protected.pop('support_assets')
    for row in protected['bodies'].values(): row['operations'].pop(S.OPERATION_ID,None)
    value={'version':1,'operation_id':S.OPERATION_ID,'changes':changes,
           'people_sha256':people_sha256,'protected_graph_sha256':E.content_digest(protected),
           'support_assets':deepcopy(b['support_assets'])}
    return {**value,'content_sha256':E.content_digest(value)}


def replay_patch(current,patch,*,undo,people_state,expected_bank_sha256):
    out=check(current)
    if graph_digest(out)!=E.digest(expected_bank_sha256): raise ValueError('Body graph changed before torso length history replay')
    if type(undo) is not bool or type(patch) is not dict or set(patch)!={'version','operation_id','changes','people_sha256','protected_graph_sha256','support_assets','content_sha256'}:
        raise ValueError('Invalid torso length history patch')
    payload={k:v for k,v in patch.items() if k!='content_sha256'}
    if type(patch['version']) is not int or patch['version']!=1 or patch['operation_id']!=S.OPERATION_ID or E.content_digest(payload)!=patch['content_sha256']:
        raise ValueError('Torso length history patch changed')
    if people_digest(people_state)!=patch['people_sha256']: raise ValueError('Canonical people graph changed; history cannot silently reidentify')
    protected=deepcopy(out); protected.pop('revision'); protected.pop('support_assets')
    for row in protected['bodies'].values(): row['operations'].pop(S.OPERATION_ID,None)
    if E.content_digest(protected)!=patch['protected_graph_sha256']: raise ValueError('Analysis, other operation or association changed after this history entry')
    before,after=('after','before') if undo else ('before','after')
    for key,change in patch['changes'].items():
        row=B.target(out,change['body_ref'])
        if key!=change['body_ref']['body_instance_id'] or row['operations'].get(S.OPERATION_ID)!=change[before]:
            raise ValueError('Torso length history would overwrite a later edit')
    for key,asset in patch['support_assets'].items():
        if key in out['support_assets'] and out['support_assets'][key]!=asset: raise ValueError('Immutable torso length support changed')
        out['support_assets'][key]=deepcopy(asset)
    for key,change in patch['changes'].items():
        if change[after] is None: out['bodies'][key]['operations'].pop(S.OPERATION_ID,None)
        else: out['bodies'][key]['operations'][S.OPERATION_ID]=deepcopy(change[after])
    out['revision']+=1
    return check(out)


def transfer_recipe(source_state,source_ref,target_state,target_ref,*,people_state,
                    expected_people_sha256,expected_source_bank_sha256,expected_target_bank_sha256,
                    confirmed_person_id,user_confirmed):
    """Parameter-only helper; NOT a claim of a reachable preset/batch workflow.

    A caller must independently prepare the actual target before publishing it.
    Source geometry, support, review and face identity are never transferred.
    """
    from .people_state import check as check_people
    people=check_people(people_state); a=check(source_state); b=check(target_state)
    if user_confirmed is not True or people_digest(people)!=E.digest(expected_people_sha256):
        raise ValueError('Torso length transfer needs explicit current canonical people graph confirmation')
    if graph_digest(a)!=E.digest(expected_source_bank_sha256) or graph_digest(b)!=E.digest(expected_target_bank_sha256):
        raise ValueError('Source or target body graph changed during torso length transfer')
    if confirmed_person_id not in people['persons']: raise ValueError('Confirmed anonymous person no longer exists')
    src=B.target(a,source_ref); dst=B.target(b,target_ref)
    for row in (src,dst):
        link=row['association']; ref=row['record']['body_ref']
        if not row['enabled'] or link is None or link['person_id']!=confirmed_person_id or link['people_association_revision']!=people['association_revision']:
            raise ValueError('Torso length transfer requires current explicit person ownership on each enabled source body')
        faces=[x for x in people['links'] if x['state']=='confirmed' and x['person_id']==confirmed_person_id and people['faces'][x['face_instance_id']]['asset_sha256']==ref['asset_sha256']]
        if len(faces)!=1: raise ValueError('Transfer requires exactly one confirmed face for this person in each source')
    item=B.operation(a,source_ref,S.OPERATION_ID); target=B.operation(b,target_ref,S.OPERATION_ID)
    if not item['enabled'] or not target['enabled'] or target['review'] is None:
        raise ValueError('Target torso length contours and visible joints must be reviewed independently before transfer')
    asset=B.support(b,target_ref,S.OPERATION_ID)
    if asset is None: raise ValueError('Target torso length support is missing')
    S.policy_check_support(asset['data'],dst['record'])
    from .torso_length_runtime import validate_face_review
    validate_face_review(asset['data'],dst,people)
    return B.set_recipe(b,target_ref,S.portable(item['recipe']),operation_id=S.OPERATION_ID,operation_policies=S.policies())
