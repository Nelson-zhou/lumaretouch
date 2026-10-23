"""Operation policies and immutable source-owned supports for ONE body bank.

Only implemented operations have policies. Unknown operation payloads survive
round-trips as unapplied intent; an enabled unknown operation blocks rendering.
An extension supplies an explicit policy, never an import name from project data.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from typing import Callable
from . import body_pose_evidence as E

SHOULDER_OPERATION='lnx.shoulder_shape.v1'
MAX_OPERATIONS=32
MAX_SUPPORT_BYTES=4*1024*1024


@dataclass(frozen=True)
class OperationPolicy:
    operation_id:str
    neutral:Callable
    check_recipe:Callable
    is_active:Callable
    required_anchors:tuple
    support_kind:str|None=None
    check_support:Callable|None=None  # (data, measured_body_record) -> checked data
    min_visibility:float=.8
    min_presence:float=.8


def policies(extra=None):
    from . import shoulder_shape_state as S
    shoulder=OperationPolicy(S.OPERATION_ID,S.neutral,S.check,S.active,tuple(E.ANCHORS))
    from . import leg_shape_state as L, arm_shape_state as A, waist_shape_state as W
    result={SHOULDER_OPERATION:shoulder,L.OPERATION_ID:L.policy(),**A.policies(),W.OPERATION_ID:W.policy()}
    for key,policy in (extra or {}).items():
        E.token(key)
        if not isinstance(policy,OperationPolicy) or policy.operation_id!=key:raise ValueError('Body operation policy identity mismatch')
        if key in result and policy!=result[key]:raise ValueError('A built-in body policy cannot be replaced by project data')
        if not policy.required_anchors or len(set(policy.required_anchors))!=len(policy.required_anchors) or any(type(i) is not int or not 0<=i<33 for i in policy.required_anchors):raise ValueError('Operation policy needs explicit actual landmark indices')
        if not 0<=policy.min_visibility<=1 or not 0<=policy.min_presence<=1:raise ValueError('Invalid operation visibility policy')
        if policy.support_kind is not None:
            E.token(policy.support_kind)
            if not callable(policy.check_support):raise ValueError('Source-owned support needs its real operation validator')
        result[key]=policy
    return result


def require_policy(operation_id,operation_policies=None):
    E.token(operation_id);policy=policies(operation_policies).get(operation_id)
    if policy is None:raise ValueError('Body operation is retained but has no installed consumer/policy: '+operation_id)
    return policy


def json_data(value,*,max_bytes=65536):
    def walk(item,depth):
        if depth>12:raise ValueError('Body operation data nesting exceeds budget')
        if item is None or type(item) in (str,bool,int,float):
            if type(item) in (int,float) and not math.isfinite(item):raise ValueError('Nonfinite body operation data')
            if type(item) is str and len(item)>8192:raise ValueError('Body operation string exceeds budget')
            return
        if type(item) is dict:
            if len(item)>4096 or any(type(k) is not str or len(k)>256 for k in item):raise ValueError('Invalid body operation object')
            for child in item.values():walk(child,depth+1)
        elif type(item) is list:
            if len(item)>65536:raise ValueError('Body operation list exceeds budget')
            for child in item:walk(child,depth+1)
        else:raise ValueError('Body operations store data, not arrays/executable objects')
    walk(value,0)
    if len(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())>max_bytes:raise ValueError('Body operation data exceeds byte budget')
    return deepcopy(value)


def empty_operation(operation_id=SHOULDER_OPERATION,*,operation_policies=None):
    policy=require_policy(operation_id,operation_policies)
    return {'enabled':True,'recipe':policy.check_recipe(policy.neutral()),'review':None,'support_sha256':None}


def support_record(operation_id,record,kind,data,*,operation_policies=None):
    record=E.check(record);policy=require_policy(operation_id,operation_policies)
    if policy.support_kind is None or kind!=policy.support_kind:raise ValueError('This operation does not accept that source support kind')
    checked=json_data(policy.check_support(json_data(data,max_bytes=MAX_SUPPORT_BYTES),record),max_bytes=MAX_SUPPORT_BYTES)
    return {'version':1,'operation_id':operation_id,'body_ref':E.ref(record['body_ref']),'points_sha256':record['points_sha256'],'source':E.source(record['source']),'kind':kind,'data':checked,'data_sha256':E.content_digest(checked)}


def check_support_record(value):
    keys={'version','operation_id','body_ref','points_sha256','source','kind','data','data_sha256'}
    if type(value) is not dict or set(value)!=keys or type(value['version']) is not int or value['version']!=1:raise ValueError('Invalid body support asset')
    E.token(value['operation_id']);E.token(value['kind']);ref=E.ref(value['body_ref']);source=E.source(value['source'])
    E.digest(value['points_sha256']);E.digest(value['data_sha256'])
    if ref['asset_sha256']!=source['sha256'] or E.content_digest(json_data(value['data'],max_bytes=MAX_SUPPORT_BYTES))!=value['data_sha256']:raise ValueError('Body support content/source changed')
    return deepcopy(value)


def check_operation(operation_id,value,record,assets,bank_revision,*,operation_policies=None):
    E.token(operation_id)
    if type(value) is not dict or set(value)!={'enabled','recipe','review','support_sha256'} or type(value['enabled']) is not bool:raise ValueError('Invalid body operation entry')
    recipe=json_data(value['recipe'])
    if type(recipe) is not dict or type(recipe.get('version')) is not int or recipe['version']<1:raise ValueError('Body operation recipe needs its own explicit version')
    policy=policies(operation_policies).get(operation_id)
    if policy is not None:policy.check_recipe(recipe)
    support=None;key=value['support_sha256']
    if key is not None:
        E.digest(key);support=assets.get(key)
        if support is None or E.content_digest(support)!=key:raise ValueError('Body operation support asset is missing/changed')
        check_support_record(support)
        if support['operation_id']!=operation_id or support['body_ref']!=record['body_ref'] or support['points_sha256']!=record['points_sha256'] or support['source']!=record['source']:raise ValueError('Body support cannot cross operations, sources, bodies or analysis revisions')
        if policy is not None:
            if policy.support_kind!=support['kind'] or policy.check_support is None:raise ValueError('Body support is not admitted by this operation')
            if policy.check_support(deepcopy(support['data']),record)!=support['data']:raise ValueError('Retained body support no longer matches its operation schema')
    review=value['review']
    if review is not None:
        keys={'operation_id','body_ref','points_sha256','visible_anchors','ownership_confirmed','review_revision','support_sha256'}
        if type(review) is not dict or set(review)!=keys or review['operation_id']!=operation_id or E.ref(review['body_ref'])!=record['body_ref'] or review['points_sha256']!=record['points_sha256'] or review['ownership_confirmed'] is not True or review['support_sha256']!=key:raise ValueError('Body visibility review is not operation/source/support owned')
        anchors=review['visible_anchors']
        if type(anchors) is not list or not anchors or len(set(anchors))!=len(anchors) or any(type(i) is not int or not 0<=i<33 for i in anchors):raise ValueError('Invalid operation-specific visible anchor review')
        if policy is not None and anchors!=list(policy.required_anchors):raise ValueError('Another operation’s anchor review cannot authorize this operation')
        if policy is not None and policy.support_kind is not None and support is None:raise ValueError('This operation requires separately reviewed visible source support')
        if policy is not None:
            for index in policy.required_anchors:
                p=record['points'][index]
                if p['visibility']<policy.min_visibility or p['presence']<policy.min_presence or not (0<p['x']<1 and 0<p['y']<1):raise ValueError('Retained review cannot override an unverifiable operation anchor')
        if E.revision(review['review_revision'])>bank_revision:raise ValueError('Future body operation review')
    return deepcopy(value)


def active_operations(row,*,operation_policies=None):
    """Unknown enabled intent refuses conservatively, never silently exports."""
    if not row['enabled']:return ()
    result=[]
    for operation_id,value in row['operations'].items():
        if not value['enabled']:continue
        policy=require_policy(operation_id,operation_policies)
        if policy.is_active(value['recipe']):result.append(operation_id)
    return tuple(result)


def require_consumers(state,asset_sha256,consumer_ids,*,operation_policies=None):
    known=set(consumer_ids)
    for row in state['bodies'].values():
        if row['record']['source']['sha256']!=asset_sha256:continue
        for operation_id in active_operations(row,operation_policies=operation_policies):
            if operation_id not in known:raise ValueError('Active body intent has no prepared render consumer: '+operation_id)


def field_binding(row,operation_id):
    """Prepared numeric fields bind edits/reviews/support, not only stable identity."""
    E.token(operation_id)
    if operation_id not in row['operations']:raise ValueError('Prepared operation has no current body intent')
    return E.content_digest({'version':1,'operation_id':operation_id,'record':row['record'],'enabled':row['enabled'],'association':row['association'],'operation':row['operations'][operation_id]})
