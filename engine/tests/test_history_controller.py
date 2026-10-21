"""History transactions through explicit ports, independent of renderer implementation."""
from copy import deepcopy
from dataclasses import replace
from lumaretouch_engine.history_controller import HistoryController, HistoryPorts
from lumaretouch_engine.history_policy import state_signature


def fixture():
    active=[{'_proxy':(10,20),'value':2}];events=[];restores=[];remember=[];dirty=[]
    def restore(snapshot,mode):
        active[0]=deepcopy(snapshot);restores.append(mode)
        return {'event':'frame','render_ms':1}
    ports=HistoryPorts(lambda:deepcopy(active[0]),state_signature,restore,lambda action:None,
        lambda:remember.append(True),lambda:deepcopy(active[0]),lambda:dirty.append(True))
    c=HistoryController(ports,events.append,lambda:1000,3,250)
    c.undo=[{'_proxy':(10,20),'value':1}]
    return c,active,events,restores,remember,dirty


def test_success_moves_stacks_only_after_restore_and_reports_before_frame():
    c,active,events,restores,remember,_=fixture();c.handle_command({'action':'undo'})
    assert active[0]['value']==1 and c.undo==[] and c.redo[0]['value']==2
    assert restores==['history_undo'] and remember==[True]
    assert [event['event'] for event in events]==['history_state','frame']


def test_failed_restore_rolls_back_without_moving_history():
    c,active,events,restores,_,_=fixture();original=c.ports.restore_frame
    def restore(snapshot,mode):
        if mode=='history_undo':active[0]={'broken':True};raise RuntimeError('render')
        return original(snapshot,mode)
    c.ports=replace(c.ports,restore_frame=restore);before=deepcopy(c.undo)
    c.handle_command({'action':'undo'})
    assert active[0]['value']==2 and c.undo==before and c.redo==[]
    assert restores==['history_rollback'] and events[-1]['event']=='error'
    assert not any(event['event']=='engine_warn' for event in events)


def test_failed_rollback_warns_without_discarding_undo_snapshot():
    c,_,events,_,_,_=fixture()
    def fail(snapshot,mode):raise RuntimeError(mode)
    c.ports=replace(c.ports,restore_frame=fail);c.handle_command({'action':'undo'})
    assert len(c.undo)==1 and c.redo==[]
    assert [event['event'] for event in events]==['engine_warn','error']


def test_proxy_mismatch_never_restores_and_clear_bypasses_busy_guard():
    c,_,events,restores,remember,_=fixture();c.undo[0]['_proxy']=(20,20)
    c.handle_command({'action':'undo'});assert restores==[] and events[-1]['event']=='error'
    def unexpected(action):raise AssertionError('clear must bypass guard')
    c.ports=replace(c.ports,guard=unexpected);c.handle_command({'action':'clear'})
    assert c.undo==[] and c.redo==[] and remember==[True]


def test_binding_copies_stack_lists_and_curve_gesture_can_return_to_start():
    c,active,_,_,_,dirty=fixture();row={'undo':[{'_proxy':(10,20),'value':1}],'redo':[]}
    c.bind(row);row['undo'].clear();assert len(c.undo)==1
    c.bind(None);before=deepcopy(active[0]);active[0]['value']=3
    c.record('curves:gesture:one',before);assert len(c.undo)==1 and dirty==[True]
    changed=deepcopy(active[0]);active[0]=before
    c.record('curves:gesture:one',changed);assert c.undo==[] and c.group==''


def test_engine_aliases_bind_without_constructor_and_resolve_emitter_late(monkeypatch):
    from lumaretouch_engine import server
    e=server.Engine.__new__(server.Engine);e._undo=[];e._redo=[]
    e.doc_state=lambda:{'known':True}
    row={'undo':[{'saved':True}],'redo':[]};e._history_bind(row);row['undo'].clear()
    events=[];monkeypatch.setattr(server,'emit',events.append)
    e.cmd_history({'action':'state'})
    assert len(e._undo)==1 and events[-1]['undo_steps']==1
    assert e._history_controller().undo is e._undo
