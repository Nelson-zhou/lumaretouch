"""Portable AUTO REQUEST scope, connected only through frozen-review ports.

Prepared target recipes are deliberately not accepted as portable preset input.
"""
from copy import deepcopy
from . import optics_state as S
from . import reference_color_scope as RC
OP='lnx.optics_auto.v1'
FIELDS=('_optics',)
EXCLUDED=['profile identity','guide geometry','solved matrix']


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'request'}:raise ValueError('自动镜头/透视预设只接受逐图重算请求')
    request=raw['request']
    if type(request) is not dict or set(request)!={'version','manual','auto_mode','lens_auto','excluded'} or type(request['version']) is not int or request['version']!=1:raise ValueError('自动镜头/透视请求版本或字段无效')
    manual=S.check(request['manual'])
    if S.source_bound(manual) or manual['source'] is not None or manual['lens']['enabled'] or manual['perspective']['analysis'] is not None:
        raise ValueError('自动请求不能携带任何源图配置、引导线、分析结果或身份')
    if type(request['lens_auto']) is not bool or request['auto_mode'] not in ('off','smart','horizontal','vertical') or request['excluded']!=EXCLUDED:
        raise ValueError('自动镜头/透视请求模式无效')
    return {'request':{'version':1,'manual':manual,'auto_mode':request['auto_mode'],'lens_auto':request['lens_auto'],'excluded':EXCLUDED.copy()}}


def params_of(state):
    value=S.check(state.get('_optics'))
    if value['perspective']['mode']=='guided' or value['perspective']['guides']:
        raise ValueError('引导线透视不能跨图复制；请选择仅手动参数，或改成自动模式后保存')
    return check_params({'request':S.portable(value)})


def install(state,params):
    check_params(params)
    raise ValueError('自动镜头/透视必须先对目标照片预检，不能绕过冻结的逐图分析')


def restore(state,previous):
    """Batch undo must restore the exact prior target solve, not reanalyse it."""
    state['_optics']=deepcopy(S.check(previous.get('_optics')))


def undo_key(state):
    import hashlib,json
    return hashlib.sha256(json.dumps(S.check(state.get('_optics')),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def before_params(state,ops):
    from . import scope as SC
    from . import id_background_scope as ID_BACKGROUND
    from . import fringe_repair_scope as FRINGE
    from . import spill_removal_scope as SPILL
    from . import original_shadow_scope as SHADOW
    result=SC.params_of(state,[op for op in ops if op not in (OP,RC.OP,ID_BACKGROUND.OP,FRINGE.OP,SPILL.OP,SHADOW.OP)])
    if SHADOW.OP in ops:result[SHADOW.OP]={"target_recipe_key":SHADOW.undo_key(state)}
    if SPILL.OP in ops:result[SPILL.OP]={"target_recipe_key":SPILL.undo_key(state)}
    if FRINGE.OP in ops:result[FRINGE.OP]={"target_recipe_key":FRINGE.undo_key(state)}
    if ID_BACKGROUND.OP in ops:result[ID_BACKGROUND.OP]={"target_recipe_key":ID_BACKGROUND.undo_key(state)}
    if OP in ops:result[OP]={'target_recipe_key':undo_key(state)}
    if RC.OP in ops:result[RC.OP]={"target_recipe_key":RC.undo_key(state)}
    return result


def candidate(state,modules,*,local_replace_legacy=False):
    """One shadow candidate for BOTH upstream render and final transaction."""
    from . import scope as SC
    SC.check_scope(list(modules))
    ordinary={op:params for op,params in modules.items() if op not in (OP,RC.OP)}
    return SC.apply_modules(state,ordinary,local_replace_legacy=local_replace_legacy) if ordinary else dict(state)


def verify_target(record,state,candidate_state,row,document_id,revision,params):
    from .optics_transfer_review import verify
    return verify(record,path=row['path'],document_id=document_id,revision=str(revision),state=state,params=params,candidate_state=candidate_state)


def validate_restoration(state,row):
    from . import local_mask_state as M
    from .optics_stage import OpticsStage
    recipe=S.check(state.get('_optics'))
    if recipe['source'] is not None:M.verify_source({'source':recipe['source']},row['path'],(row['src_h'],row['src_w']))
    stage=OpticsStage(recipe,(row['src_h'],row['src_w']))
    if stage.suspended:raise ValueError(stage.suspended)
