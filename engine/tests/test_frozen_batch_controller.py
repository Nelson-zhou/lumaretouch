from copy import deepcopy
from dataclasses import replace
from test_batch_sync_controller import fixture
from lumaretouch_engine.scope import OP_EXPOSURE


def preflight(c,events,docs=None,policy='skip_and_report'):
    c.handle_command({'action':'preflight','docs':[1,2] if docs is None else docs,
        'module_scope':[OP_EXPOSURE],'conflict_policy':policy,'request_id':'review'})
    result=events[-1];assert result['event']=='batch_result' and result['success']
    return result['preflight_token']


def commit(c,events,token,**extra):
    c.handle_command({'action':'commit','preflight_token':token,'request_id':'commit',**extra})
    return events[-1]


def test_frozen_source_survives_source_edit_and_duplicate_commit_does_not_apply_twice():
    c,rows,_,events,_,_=fixture();token=preflight(c,events)
    rows[0]['state']['_exposure']=(4.,0.,0.,0.,0.,0.,0.);c.versions.advance(rows[0])
    result=commit(c,events,token)
    assert result['success'] and result['source_changed_since_preflight']
    assert rows[1]['state']['_exposure'][0]==1 and rows[2]['state']['_exposure'][0]==1
    undo=deepcopy(rows[1]['undo']);bid=result['batch_id']
    again=commit(c,events,token)
    assert again['success'] and again['replayed'] and again['batch_id']==bid and rows[1]['undo']==undo


def test_edit_then_undo_same_value_still_conflicts_and_skips_only_that_target():
    c,rows,_,events,_,_=fixture();token=preflight(c,events)
    c.versions.advance(rows[1]);c.versions.advance(rows[1])
    result=commit(c,events,token)
    assert result['success'] and result['targets']==[2]
    assert rows[1]['state']['_exposure'][0]==0 and rows[1]['undo']==[]
    assert result['skipped'][0]['index']==1


def test_recheck_conflict_writes_no_parameters_or_history():
    c,rows,_,events,_,_=fixture();token=preflight(c,events,policy='recheck')
    c.versions.advance(rows[1]);before=deepcopy(rows)
    result=commit(c,events,token)
    assert not result['success'] and rows==before and c.ledger=={}


def test_reorder_resolves_original_identity_and_batch_undo_uses_same_identity():
    c,rows,current,events,_,_=fixture();target=rows[1];token=preflight(c,events,docs=[1])
    rows[1],rows[2]=rows[2],rows[1]
    result=commit(c,events,token)
    assert result['success'] and result['targets']==[2] and target['state']['_exposure'][0]==1
    rows[1],rows[2]=rows[2],rows[1]
    c.handle_command({'action':'undo','batch_id':result['batch_id']})
    assert target['state']['_exposure'][0]==0


def test_readded_same_path_and_workspace_replacement_are_not_old_targets():
    c,rows,_,events,_,_=fixture();token=preflight(c,events)
    rows[1]=deepcopy(rows[1])
    result=commit(c,events,token)
    assert result['success'] and result['targets']==[2] and rows[1]['state']['_exposure'][0]==0
    token=preflight(c,events);c.versions.new_workspace();before=deepcopy(rows)
    assert not commit(c,events,token)['success'] and rows==before


def test_missing_source_does_not_substitute_current_source():
    c,rows,current,events,_,_=fixture();token=preflight(c,events,docs=[1])
    rows.pop(0);current[0]=1;rows[1]['state']['_exposure']=(3.,0.,0.,0.,0.,0.,0.)
    result=commit(c,events,token)
    assert result['success'] and result['source_missing'] and rows[0]['state']['_exposure'][0]==1


def test_commit_cannot_modify_reviewed_modules_or_targets_and_guard_errors_are_correlated():
    c,rows,_,events,_,_=fixture();token=preflight(c,events);before=deepcopy(rows)
    result=commit(c,events,token,docs=[0])
    assert not result['success'] and rows==before
    c.editor=replace(c.editor,guard=lambda name:'busy')
    result=commit(c,events,token)
    assert result['event']=='batch_result' and result['request_id']=='commit' and not result['success']


def test_live_failure_rolls_back_before_any_parked_target_changes():
    c,rows,_,events,_,_=fixture();before=deepcopy(rows)
    def replay(state,**kw):
        if 'rollback' not in kw['replayed_for']:raise RuntimeError('render failed')
        rows[0]['state']=deepcopy(state);return {'event':'frame'}
    c.editor=replace(c.editor,replay=replay)
    c.handle_command({'action':'commit','docs':[1,0,2],'module_scope':[OP_EXPOSURE]})
    assert rows[1]==before[1] and rows[2]==before[2] and c.ledger=={}
    assert rows[0]['state']==before[0]['state']


def test_parked_commit_and_undo_mark_project_dirty_but_preflight_does_not():
    c,rows,_,events,_,_=fixture();dirty=[]
    c.editor=replace(c.editor,mark_dirty=lambda:dirty.append(True))
    token=preflight(c,events,docs=[1]);assert dirty==[]
    result=commit(c,events,token);assert result['success'] and dirty==[True]
    c.handle_command({'action':'undo','batch_id':result['batch_id']});assert len(dirty)==2


def test_completed_token_replays_during_busy_guard_and_retains_stable_outcomes():
    c,rows,_,events,_,_=fixture();token=preflight(c,events,docs=[1])
    first=commit(c,events,token);assert first['success']
    c.editor=replace(c.editor,guard=lambda name:'export is busy')
    again=commit(c,events,token)
    assert again['success'] and again['replayed'] and again['target_outcomes']==first['target_outcomes']
    assert first['target_outcomes'][0]['document_id']==c.versions.version(rows[1]).document_id
    assert first['target_outcomes'][0]['result_revision']!=first['target_outcomes'][0]['expected_revision']


def test_recheck_errors_keep_per_target_version_evidence():
    c,rows,_,events,_,_=fixture();token=preflight(c,events,policy='recheck')
    c.versions.advance(rows[1]);result=commit(c,events,token)
    assert not result['success'] and len(result['target_outcomes'])==2
    conflict=result['target_outcomes'][0]
    assert conflict['document_id']==c.versions.version(rows[1]).document_id
    assert conflict['expected_revision']!=conflict['current_revision'] and conflict['outcome']=='conflict'


def test_later_exhausted_target_prevents_any_live_or_parked_write():
    from lumaretouch_engine.document_versions import KEY,MAX_REVISION
    c,rows,_,events,replays,_=fixture();rows[2][KEY]['revision']=MAX_REVISION;before=deepcopy(rows)
    c.handle_command({'action':'commit','docs':[0,1,2],'module_scope':[OP_EXPOSURE]})
    assert rows==before and not replays and c.ledger=={} and events[-1]['event']=='error'
