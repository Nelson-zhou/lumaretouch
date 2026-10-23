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


def _source_assets(bank):
    found=set(bank['analysis_runs'])
    found.update(row['record']['source']['sha256'] for row in bank['bodies'].values())
    found.update(asset['source']['sha256'] for asset in bank['support_assets'].values())
    return found


def _frame_identity(snapshot,bank):
    """Validate passive evidence without inference or relabelling its source."""
    from .creative_derived_source import record, binding
    base=record(snapshot)
    proof=snapshot.get('_people_history')
    known=_source_assets(bank)
    if base is not None:
        source=binding(snapshot)
        expected=source['sha256']
        for value in ([row['record']['source'] for row in bank['bodies'].values()]
                      +[asset['source'] for asset in bank['support_assets'].values()]):
            if any(value[key]!=source[key] for key in ('sha256','width','height')):
                raise ValueError('Body history evidence belongs to another creative source extent')
    else:
        expected=proof['asset_sha256'] if proof is not None else next(iter(known),None)
    if len(known)>1 or known-({expected} if expected is not None else set()):
        raise ValueError('Body history bank contains another source asset')
    if proof is not None and expected is not None and proof['asset_sha256']!=expected:
        raise ValueError('Body history and portrait history source disagree')
    return None if base is None else base['id']


def decorate(before,after):
    if D.KEY not in before and D.KEY not in after:return before
    a=D.bank(before);b=D.bank(after)
    left=_frame_identity(before,a);right=_frame_identity(after,b)
    if left!=right:
        # A creative return changes the entire immutable source. Each complete
        # frame retains its own bank; append-only sparse patches are for edits
        # within a source, never for transferring supports across two sources.
        out=dict(before);out.pop(KEY,None)
        return out
    assets=_source_assets(a)|_source_assets(b)
    if len(assets)>1:raise ValueError('Document body history cannot span source assets')
    out=dict(before);out[KEY]={'version':1,'patch':P.history_patch(a,b)}
    return out


def restore(current,snapshot,*,current_state=None):
    """Keep fences monotonic, with no support-bank merge across pixel sources."""
    current=B.check(current);desired=D.bank(snapshot)
    target=_frame_identity(snapshot,desired)
    if current_state is not None:
        origin=_frame_identity(current_state,current)
        if origin!=target:
            if KEY in snapshot:raise ValueError('Source-switch body history cannot use a sparse patch')
            desired['revision']=max(current['revision'],desired['revision'])+1
            desired['association_revision']=max(current['association_revision'],desired['association_revision'])+1
            return B.check(desired)
    elif target is not None:
        raise ValueError('Derived body history restore needs the current source state')
    if len(_source_assets(current)|_source_assets(desired))>1:
        raise ValueError('Same-source body restore cannot join unrelated source banks')
    if KEY in snapshot:
        transition=validate_transition(snapshot[KEY])
        restored=P.replay_patch(current,transition['patch'],undo=True,expected_association_revision=current['association_revision'])
        _frame_identity(snapshot,restored)
        return restored
    for key,asset in current['support_assets'].items():
        if key in desired['support_assets'] and desired['support_assets'][key]!=asset:raise ValueError('Body history support hash collision')
        desired['support_assets'][key]=deepcopy(asset)
    _frame_identity(snapshot,desired)
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
    state=D.bank(snapshot);found=_source_assets(state)
    if KEY in snapshot:
        patch=validate_transition(snapshot[KEY])['patch']
        found.update(patch['analysis_runs_before']);found.update(patch['analysis_runs_after'])
        found.update(asset['source']['sha256'] for asset in patch['support_assets'].values())
        found.update(row['record']['source']['sha256'] for change in patch['changes'].values() for row in change.values() if row is not None)
    return found
