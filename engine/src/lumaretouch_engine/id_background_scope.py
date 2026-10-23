"""One portable scope: source reviews, spill vectors and assets stay target-owned.

The operation ID remains stable. Its versioned portable recipe admits v1 and
v2 for faithful persisted recipes. Changing spill through whole-ID transfer is
now refused until that wider route has visual review; use the dedicated scalar
spill scope. Target-owned coverage and scoped historical restoration survive.
"""
from . import id_background_state as S, id_background_assets as A
from . import local_mask_state as M
OP='lnx.id_background.v1'
FIELDS=('_id_background','_id_background_bundle')


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'}:raise ValueError('证件照背景预设仅接受参数配方')
    return {'recipe':S.check_portable(raw['recipe'])}


def params_of(state):return {'recipe':S.portable(state.get('_id_background'))}


def install(state,params):
    prior=S.check(state.get('_id_background'))
    value=S.apply_portable(prior,check_params(params)['recipe'])
    # Whole-ID transfer is not the dedicated spill visual review route. Never
    # let that wider module bypass the new per-target spill acknowledgment.
    from . import spill_removal_state as SPILL
    before_spill,after_spill=S.spill_of(prior),S.spill_of(value)
    if value!=prior and (SPILL.portable(before_spill)!=SPILL.portable(after_spill)
            or SPILL.active(before_spill) or SPILL.active(after_spill)):
        raise ValueError('整套证件照背景迁移涉及祛反光变更，尚无整套目标画面审核；请分别审核背景和专用祛反光模块，不会绕过逐图确认')
    if S.active(value):
        from .studio_background_state import active as studio_active
        from .sky_replacement_state import check as sky_check
        if (state.get('_bg') or {}).get('active') or studio_active(state.get('_studio_background')) or sky_check(state.get('_sky_replacement'))['enabled']:
            raise ValueError('目标已启用互斥的背景效果，请先选择保留哪个效果')
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(state.get('_id_background_bundle'))
        if bundle is None or bundle['binding']!=value['background']['asset']:raise ValueError('目标自己的背景素材身份不匹配')
    state['_id_background']=value


def validate_target(state,path,shape):
    value=S.check(state.get('_id_background'))
    if state.get('_creative_base') is not None:
        from .creative_derived_id_background import validate_state
        validate_state(state)  # Target-owned reviews only; planner admission stays fenced.
    elif value['source'] is not None:M.verify_source(value,path,shape)
    if S.active(value):
        from .studio_background_state import active as studio_active
        from .sky_replacement_state import check as sky_check
        if (state.get('_bg') or {}).get('active') or studio_active(state.get('_studio_background')) or sky_check(state.get('_sky_replacement'))['enabled']:
            raise ValueError('证件照背景恢复与目标当前背景效果冲突；整组不修改')
        reviewed=value['support'][value['selected_support']]
        if reviewed is None or reviewed['mask']['source']!=value['source']:
            raise ValueError('目标缺少自己独立审核的主体/物品范围；不会复制别人的蒙版')
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(state.get('_id_background_bundle'))
        if bundle is None or bundle['binding']!=value['background']['asset']:raise ValueError('目标背景素材身份不匹配')


def undo_key(state):
    import hashlib,json
    value=S.check(state.get('_id_background'))
    bundle=state.get('_id_background_bundle')
    binding=A.check_bundle(bundle)['binding'] if bundle is not None else None
    return hashlib.sha256(json.dumps({'recipe':value,'asset':binding},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def restore(state,previous):
    from copy import deepcopy
    value=S.check(previous.get('_id_background'))
    bundle=previous.get('_id_background_bundle')
    if bundle is not None:A.check_bundle(bundle)
    state['_id_background']=value
    state['_id_background_bundle']=deepcopy(bundle)
