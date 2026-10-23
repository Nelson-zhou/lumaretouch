"""Body patches decorate the existing history owner; no second undo stack."""
from copy import deepcopy
from . import body_pose_project as D,body_pose_state as B,body_pose_evidence as E,shoulder_shape_project as P
KEY='_body_pose_transition'


def validate_transition(value):
    if type(value) is not dict or set(value)!={'version','patch'} or value['version']!=1:raise ValueError('Invalid body history transition')
    patch=value['patch'];keys={'version','changes','before_association_revision','after_association_revision','analysis_runs_before','analysis_runs_after','support_assets'}
    if type(patch) is not dict or set(patch)!=keys or patch['version']!=2 or type(patch['changes']) is not dict or len(patch['changes'])>4096:raise ValueError('Invalid body history patch')
    for name in ('before_association_revision','after_association_revision'):E.revision(patch[name])
    for side in ('before','after'):
        state=B.empty();state['association_revision']=patch[side+'_association_revision'];state['analysis_runs']=deepcopy(patch['analysis_runs_'+side]);state['support_assets']=deepcopy(patch['support_assets'])
        for key,change in patch['changes'].items():
            if type(change) is not dict or set(change)!={'before','after'}:raise ValueError('Invalid body history change')
            row=change[side]
            if row is not None:
                state['bodies'][key]=deepcopy(row)
                state['revision']=max(state['revision'],row['record']['body_ref']['analysis_revision'],*(item['review']['review_revision'] for item in row['operations'].values() if item['review'] is not None))
        B.check(state)
    return deepcopy(value)


def decorate(before,after):
    if D.KEY not in before and D.KEY not in after:return before
    a=D.bank(before);b=D.bank(after)
    assets={row['record']['source']['sha256'] for state in (a,b) for row in state['bodies'].values()}
    if len(assets)>1:raise ValueError('Document body history cannot span source assets')
    out=dict(before);out[KEY]={'version':1,'patch':P.history_patch(a,b)}
    return out


def restore(current,snapshot):
    """Current revision stays monotonic even when restoring earlier observations."""
    current=B.check(current)
    if KEY in snapshot:
        transition=validate_transition(snapshot[KEY])
        return P.replay_patch(current,transition['patch'],undo=True,expected_association_revision=current['association_revision'])
    desired=D.bank(snapshot)
    for key,asset in current['support_assets'].items():
        if key in desired['support_assets'] and desired['support_assets'][key]!=asset:raise ValueError('Body history support hash collision')
        desired['support_assets'][key]=deepcopy(asset)
    desired['revision']=max(current['revision'],desired['revision'])+1
    desired['association_revision']=max(current['association_revision'],desired['association_revision'])+1
    return B.check(desired)


def signature(packed):
    state=P.unpack(packed)
    # Fences and retained, unreferenced immutable assets do not change pixels or
    # user intent. Operation entries keep all actual recipe/review/support data.
    return {'bodies':state['bodies'],'analysis_runs':state['analysis_runs']}


def assets(snapshot):
    """Include after-side observations in the first analysis undo entry."""
    state=D.bank(snapshot);found=set(state['analysis_runs'])
    found.update(row['record']['source']['sha256'] for row in state['bodies'].values())
    if KEY in snapshot:
        patch=validate_transition(snapshot[KEY])['patch']
        found.update(patch['analysis_runs_before']);found.update(patch['analysis_runs_after'])
        found.update(row['record']['source']['sha256'] for change in patch['changes'].values() for row in change.values() if row is not None)
    return found
