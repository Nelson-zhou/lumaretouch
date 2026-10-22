"""Portable reference intent, never source-fitted correction/geometry reuse."""
from copy import deepcopy
from . import reference_color_state as S


def check_params(value):
    if type(value) is not dict or set(value)!={'version','strength','reference'}:
        raise ValueError('参考色彩预设只能包含版本、程度与样片身份，不能传入拟合增益')
    if type(value['version']) is not int or value['version']!=1: raise ValueError('参考色彩预设版本无效')
    amount=S.number(value['strength'],0,1);reference=value['reference']
    if reference is None:
        if amount: raise ValueError('参考色彩预设缺少样片')
    else:
        # Validate using a target-neutral recipe; no guessed target identity.
        test=S.empty();test['reference']=reference;S.check(test)
    return {'version':1,'strength':amount,'reference':deepcopy(reference)}


def params_of(state):
    return check_params(S.portable(state.get(S.KEY)))


def apply_prepared(state,params,record):
    request=check_params(params)
    if request['strength']==0: return S.install(state,S.empty())
    if record is None: raise ValueError('参考色彩必须逐目标重新对应、拟合与冻结审核；不可直接复制参数')
    # Caller must verify record against BOTH fresh source/target inputs before this hook.
    recipe=S.check(record['recipe'])
    if recipe['strength']!=request['strength'] or recipe['reference']!=request['reference']:
        raise ValueError('参考色彩预检与预设请求不一致')
    return S.install(state,recipe)

OP=S.OP
FIELDS=(S.KEY,'_reference_color_bundle')


def install(state,params):
    request=check_params(params)
    if request['strength']:raise ValueError('参考统一必须先完成目标自己的冻结预检')
    state[S.KEY]=S.empty();state['_reference_color_bundle']=None


def restore(state,previous):
    state[S.KEY]=deepcopy(S.check(previous.get(S.KEY)))
    state['_reference_color_bundle']=previous.get('_reference_color_bundle')


def undo_key(state):
    from hashlib import sha256
    from .batch_preflight import canonical
    return sha256(canonical(S.check(state.get(S.KEY))).encode()).hexdigest()


def verify_target(record,state,candidate,row,document_id,revision,params):
    from hashlib import sha256
    from .batch_preflight import canonical
    from . import reference_color_assets as A,local_mask_state as M
    from .reference_color_review import candidate_key
    request=check_params(params)
    if not request['strength']:return S.empty()
    if type(record) is not dict or record.get('proof')!=sha256(canonical({k:v for k,v in record.items() if k!='proof'}).encode()).hexdigest():
        raise ValueError('参考统一冻结预检凭据改变')
    target=record['target'];recipe=S.check(record['recipe'])
    if (target['document_id']!=document_id or target['revision']!=str(revision) or target['state_key']!=candidate_key(candidate)
            or recipe['reference']!=request['reference'] or recipe['strength']!=request['strength']):
        raise ValueError('参考统一目标状态/版本/样片与预检不符')
    M.verify_source({'source':target['source']},row['path'],(row['src_h'],row['src_w']))
    if recipe['source']!=target['source'] or recipe['reference']['render_sha256']!=record['reference']['render_sha256']:
        raise ValueError('参考统一来源摘要不符')
    A.load(A.cache_root(),request['reference'])
    return recipe


def apply_verified(state,recipe):
    from . import reference_color_assets as A
    state[S.KEY]=S.check(recipe)
    state['_reference_color_bundle']=A.bundle(recipe['reference']) if recipe['reference'] is not None else None
    return state
