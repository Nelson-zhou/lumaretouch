"""Batch lifecycle exercised through explicit ports, without importing Engine."""
from copy import deepcopy
from dataclasses import replace
from lumaretouch_engine.batch_sync import BatchDocuments, BatchEditor, BatchSyncController
from lumaretouch_engine.scope import OP_EXPOSURE


def fixture():
    rows=[{'path':f'/photo-{i}.png','state':{'_exposure':(ev,0.,0.,0.,0.,0.,0.),'untouched':'keep'},'undo':[],'redo':[]} for i,ev in enumerate([1.,0.,0.])]
    current=[0];events=[];replays=[];remember=[]
    def replay(state, **kw):
        rows[current[0]]['state']=deepcopy(state);replays.append(kw)
        return {'event':'frame','render_ms':1}
    documents=BatchDocuments(lambda:rows,lambda:current[0],lambda:remember.append(True),
        lambda path:next((i for i,row in enumerate(rows) if row['path']==path),-1))
    editor=BatchEditor(lambda label:None,lambda:deepcopy(rows[current[0]]['state']),replay,
        lambda row,live:('ok',''),lambda:deepcopy(rows[current[0]]['state']))
    controller=BatchSyncController(documents,editor,events.append,lambda:1.,lambda:2,2)
    for row in rows:controller.versions.version(row)
    return controller,rows,current,events,replays,remember


def test_preflight_reports_without_writing_target_or_history():
    c,rows,_,events,_,remember=fixture();before=deepcopy(rows)
    c.handle_command({'action':'preflight','docs':[1,2],'module_scope':[OP_EXPOSURE]})
    assert rows==before and c.ledger=={} and c.sequence==0
    assert events[-1]['event']=='batch_preflight' and events[-1]['ok']==2
    assert remember==[True]


def test_commit_updates_only_scoped_values_and_nonactive_history():
    c,rows,_,events,replays,_=fixture();rows[1]['redo']=[{'old':True}]
    c.handle_command({'action':'commit','docs':[1,2],'module_scope':[OP_EXPOSURE]})
    assert not replays
    assert rows[1]['state']['_exposure'][0]==1 and rows[1]['state']['untouched']=='keep'
    assert rows[1]['undo'][0]['_exposure'][0]==0 and rows[1]['redo']==[]
    bid=events[-1]['batch_id'];assert c.summary()['undoable']==[bid]
    assert c.summary()['last_result']['applied']==[1,2]


def test_undo_preserves_later_edits_and_restores_only_unchanged_targets():
    c,rows,_,events,_,_=fixture()
    c.handle_command({'action':'commit','docs':[1,2],'module_scope':[OP_EXPOSURE]})
    bid=c.summary()['last'];rows[1]['state']['_exposure']=(3.,0.,0.,0.,0.,0.,0.)
    c.handle_command({'action':'undo','batch_id':bid})
    assert rows[1]['state']['_exposure'][0]==3 and rows[2]['state']['_exposure'][0]==0
    assert events[-1]['restored']==[2] and events[-1]['conflicts'][0]['index']==1
    assert c.summary()['undoable']==[]


def test_active_target_uses_replay_without_duplicate_document_history():
    c,rows,_,events,replays,_=fixture()
    c.handle_command({'action':'commit','docs':[0],'module_scope':[OP_EXPOSURE]})
    assert len(replays)==1 and replays[0]['mode']=='batch'
    assert rows[0]['undo']==[] and events[-1]['event']=='frame'


def test_replaced_document_rows_are_looked_up_each_command():
    c,rows,_,events,_,_=fixture();holder=[rows]
    c.documents=replace(c.documents,rows=lambda:holder[0],
        index_of=lambda path:next((i for i,row in enumerate(holder[0]) if row['path']==path),-1))
    c.handle_command({'action':'preflight','docs':[1],'module_scope':[OP_EXPOSURE]})
    holder[0]=deepcopy(rows);holder[0][1]['path']='/replacement.png'
    c.handle_command({'action':'preflight','docs':['/replacement.png'],'module_scope':[OP_EXPOSURE]})
    assert events[-1]['targets'][0]['path']=='/replacement.png'


def test_engine_compatibility_aliases_and_late_emitter_patch(monkeypatch):
    from lumaretouch_engine import server
    engine=server.Engine.__new__(server.Engine)
    engine._batch_seq=7
    engine._batches={}
    engine._sync_last={'kind':'known'}
    events=[]
    monkeypatch.setattr(server,'emit',events.append)
    engine.cmd_batch({'action':'state'})
    assert events[-1]['event']=='batch_state'
    assert engine._batch_controller().sequence==7
    assert engine._sync_state()['last_result']=={'kind':'known'}


def test_batch_undo_preserves_later_out_of_scope_edits_for_parked_target():
    c,rows,_,_,_,_=fixture()
    c.handle_command({'action':'commit','docs':[1],'module_scope':[OP_EXPOSURE]})
    bid=c.summary()['last']
    rows[1]['state']['untouched']='later edit outside batch scope'
    rows[1]['state']['new_unrelated_layer']={'visible':True}
    c.handle_command({'action':'undo','batch_id':bid})
    assert rows[1]['state']['_exposure'][0]==0
    assert rows[1]['state']['untouched']=='later edit outside batch scope'
    assert rows[1]['state']['new_unrelated_layer']=={'visible':True}


def test_batch_undo_replays_scoped_restore_without_erasing_live_unrelated_edits():
    c,rows,current,_,replays,_=fixture()
    c.handle_command({'action':'commit','docs':[1],'module_scope':[OP_EXPOSURE]})
    bid=c.summary()['last'];current[0]=1
    rows[1]['state']['untouched']='later live edit'
    c.handle_command({'action':'undo','batch_id':bid})
    assert rows[1]['state']['_exposure'][0]==0
    assert rows[1]['state']['untouched']=='later live edit'
    assert replays[-1]['replayed_for']==f'batch_undo:{bid}'


def test_batch_ev_undo_preserves_later_white_balance_and_tone_in_shared_tuple():
    c,rows,_,_,_,_=fixture()
    c.handle_command({'action':'commit','docs':[1],'module_scope':[OP_EXPOSURE]})
    bid=c.summary()['last']
    rows[1]['state']['_exposure']=(1.,.2,-.1,.15,.1,-.2,.3)
    c.handle_command({'action':'undo','batch_id':bid})
    assert rows[1]['state']['_exposure']==(0.,.2,-.1,.15,.1,-.2,.3)
