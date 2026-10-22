"""One canonical session/project graph, with no second history or batch ledger.

The existing transaction owner stages graphs, commits them here, and stores its
normal receipts/history. Document undo uses asset-scoped slices and cannot replace
another photo's later face edits. Shared group/person mutations use existing batch
transactions; they are deliberately excluded from document-only slice restoration.
"""
from copy import deepcopy
from . import people_state as S


def document_slice(state,asset_sha256):
    state=S.check(state);S.digest(asset_sha256)
    faces={key:value for key,value in state['faces'].items() if value['asset_sha256']==asset_sha256}
    overrides=[x for x in state['overrides'] if (x['scope']=='face' and x['target_id'] in faces)
               or (x['scope']=='all_people' and x['target_id']==asset_sha256)]
    return {'asset_sha256':asset_sha256,'faces':faces,'overrides':overrides,
            'unresolved_legacy':[x for x in state['unresolved_legacy'] if x['asset_sha256']==asset_sha256],
            'analysis_run':deepcopy(state['analysis_runs'].get(asset_sha256)),
            'association_revision':state['association_revision']}


def affected_assets(before,after):
    """Conservative mutation fences, including inherited cross-photo parameters."""
    assets={f['asset_sha256'] for s in (before,after) for f in s['faces'].values()}
    assets|={x['target_id'] for s in (before,after) for x in s['overrides'] if x['scope']=='all_people'}
    assets|={asset for s in (before,after) for asset in s['analysis_runs']}
    direct={asset for asset in assets if document_slice(before,asset)!=document_slice(after,asset)}
    shared=lambda s: (s['persons'],s['groups'],s['links'],[x for x in s['overrides'] if x['scope'] in ('person','group')])
    # Shared changes conservatively invalidate all open photos. Over-invalidating
    # review is safe; silently using a stale confirmed association is not.
    return assets if shared(before)!=shared(after) else direct


class PeopleGraphOwner:
    """Derived monotonic fences live outside rewindable history state."""
    def __init__(self,state=None):
        self._state=S.check(S.empty() if state is None else state)
        self.fence=0
        self.association_fence=self._state['association_revision']
        self.asset_fences={f['asset_sha256']:0 for f in self._state['faces'].values()}

    def snapshot(self):return S.check(self._state)

    def capture_document(self,asset_sha256):
        result=document_slice(self._state,asset_sha256)
        result['asset_fence']=self.asset_fences.get(asset_sha256,0)
        result['association_fence']=self.association_fence
        return result

    def commit(self,candidate,*,expected_fence):
        """Existing receipt/batch owner calls only after complete preparation."""
        if expected_fence!=self.fence:raise ValueError('Canonical people graph changed during transaction')
        value=S.check(candidate);before=self._state
        if value['association_revision']<self.association_fence:
            raise ValueError('Association fence cannot rewind with an old snapshot')
        affected=affected_assets(before,value)
        associations=(before['persons'],before['groups'],before['links'])!=(value['persons'],value['groups'],value['links'])
        if associations:
            self.association_fence=max(self.association_fence+1,value['association_revision'])
        value['association_revision']=self.association_fence
        value['revision']=max(before['revision']+1,value['revision'])
        value=S.check(value)
        self._state=value;self.fence+=1
        for asset in affected:self.asset_fences[asset]=self.asset_fences.get(asset,0)+1
        return self.snapshot()

    def stage_document_restore(self,snapshot,*,expected_asset_fence,expected_association_fence):
        """A local undo candidate, not a commit and not a parallel undo engine."""
        asset=S.digest(snapshot['asset_sha256'])
        if expected_asset_fence!=self.asset_fences.get(asset,0):raise ValueError('This photo changed after history capture')
        if expected_association_fence!=self.association_fence or snapshot['association_fence']!=self.association_fence:
            raise ValueError('Associations changed; review shared history through the batch transaction owner')
        out=self.snapshot();current={k for k,f in out['faces'].items() if f['asset_sha256']==asset}
        restored=set(snapshot['faces'])
        if any(f['asset_sha256']!=asset or (key in out['faces'] and key not in current) for key,f in snapshot['faces'].items()):
            raise ValueError('Document history cannot replace another source face')
        if any(not ((x['scope']=='face' and x['target_id'] in restored) or (x['scope']=='all_people' and x['target_id']==asset)) for x in snapshot['overrides']):
            raise ValueError('Document history cannot replace shared person/group parameters')
        if any(x['asset_sha256']!=asset for x in snapshot['unresolved_legacy']):
            raise ValueError('Document history cannot replace another source archive')
        removed=current-restored
        if any(x['face_instance_id'] in removed for x in out['links']) or any(removed&set(g['face_ids']) for g in out['groups'].values()):
            raise ValueError('Undo would remove a face used by an association; use protected shared undo')
        for key in current:del out['faces'][key]
        out['faces'].update(deepcopy(snapshot['faces']))
        out['overrides']=[x for x in out['overrides'] if not ((x['scope']=='face' and x['target_id'] in current) or (x['scope']=='all_people' and x['target_id']==asset))]
        out['overrides'].extend(deepcopy(snapshot['overrides']))
        out['unresolved_legacy']=[x for x in out['unresolved_legacy'] if x['asset_sha256']!=asset]+deepcopy(snapshot['unresolved_legacy'])
        if snapshot['analysis_run'] is None:out['analysis_runs'].pop(asset,None)
        else:out['analysis_runs'][asset]=deepcopy(snapshot['analysis_run'])
        out['revision']+=1
        return S.check(out)
