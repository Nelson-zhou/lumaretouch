"""Sparse people patches attached to the existing document history entries.

Undo changes only leaves/instances changed by that gesture. Later unrelated face
or photo edits remain intact; overlapping later changes cause protected refusal.
"""
from copy import deepcopy
from . import people_state as S
from .people_graph_patch import between

KEY='_people_transition'


def scoped_state(snapshot):
    out=S.empty();out['faces']=deepcopy(snapshot['faces']);out['overrides']=deepcopy(snapshot['overrides'])
    out['unresolved_legacy']=deepcopy(snapshot['unresolved_legacy'])
    if snapshot['analysis_run'] is not None:out['analysis_runs'][snapshot['asset_sha256']]=deepcopy(snapshot['analysis_run'])
    return S.check(out)


def decorate(before,after):
    left=before.get('_people_history');right=after.get('_people_history')
    if left is None or right is None:return before
    if left['asset_sha256']!=right['asset_sha256']:raise ValueError('Document history cannot cross source assets')
    value=dict(before)
    value[KEY]={'asset_sha256':left['asset_sha256'],'association_fence':left['association_fence'],
                'changes':between(scoped_state(left),scoped_state(right))}
    return value


def restore(owner,transition,asset):
    from .people_graph_patch import apply
    if type(transition) is not dict or set(transition)!={'asset_sha256','association_fence','changes'}:
        raise ValueError('Invalid scoped people history patch')
    if transition['asset_sha256']!=asset:raise ValueError('People history source changed')
    if not transition['changes']:return owner.snapshot()
    if transition['association_fence']!=owner.association_fence:
        raise ValueError('People source or associations changed; scoped undo refused')
    before=owner.snapshot()
    for change in transition['changes']:
        collection,key=change['collection'],change['key']
        if collection=='analysis_runs' and key!=asset:raise ValueError('History analysis belongs to another source')
        for value in (change['before'],change['after']):
            if value is None:continue
            if collection in ('faces','unresolved_legacy') and value['asset_sha256']!=asset:raise ValueError('History record belongs to another source')
            if collection=='overrides':
                if value['scope']=='all_people' and value['target_id']!=asset:raise ValueError('History defaults belong to another source')
                if value['scope']=='face':
                    face=before['faces'].get(value['target_id'])
                    if face is not None and face['asset_sha256']!=asset:raise ValueError('History face belongs to another source')
    candidate=apply(before,transition['changes'],redo=False)
    # Defensive scope validation even for manually modified project histories.
    from .people_graph_owner import document_slice
    other_assets={f['asset_sha256'] for state in (before,candidate) for f in state['faces'].values()}-{asset}
    if any(document_slice(before,key)!=document_slice(candidate,key) for key in other_assets):
        raise ValueError('Document history patch attempts to change another source')
    if any(change['collection'] in ('persons','groups','links') or
           (change['collection']=='overrides' and change['key'][0] not in ('face','all_people'))
           for change in transition['changes']):raise ValueError('Shared history belongs to the batch owner')
    return candidate
