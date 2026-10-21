"""Independent curves survive state, module sync and export selection."""
from lumaretouch_engine.server import Engine
from lumaretouch_engine import scope as S
from lumaretouch_engine.ops import curves as C


def test_curve_state_is_deep_copied_and_old_projects_are_neutral():
    e=Engine('curve-state-test')
    state=e._capture_state();state['_curves']['red'][0][1]=.1
    assert e._curves['red'][0][1]==0
    e._apply_state(state);state['_curves']['red'][0][1]=.2
    assert e._curves['red'][0][1]==.1
    old=e._fresh_doc_state();del old['_curves'];e._apply_state(old)
    assert C.is_identity(e._curves)


def test_curves_module_sync_does_not_touch_lut_or_exposure():
    e=Engine('curve-module-test');state=e._capture_state()
    sentinel=object();state['_lut']=sentinel
    spec=C.default_curves();spec['master']=[[0,.1],[1,.9]]
    result=S.apply_modules(state,{S.OP_CURVES:{'recipe':spec}})
    assert result['_lut'] is sentinel and result['_exposure']==state['_exposure']
    assert not C.is_identity(result['_curves']) and C.is_identity(state['_curves'])
    spec['master'][0][1]=.8
    assert result['_curves']['master'][0][1]==.1


def test_nonidentity_curves_prevent_16bit_neutral_passthrough():
    e=Engine('curve-export-test')
    e._curves['red'][0][1]=.1
    assert 'RGB/master 曲线' in e._master16_blockers(scale=1,sharpen=0)
    assert 'RGB/master 曲线' in Engine._master16_snapshot_blockers({'curves':e._curves})
    assert 'RGB/master 曲线' not in Engine._master16_snapshot_blockers({})


def test_gesture_identity_does_not_merge_different_drags():
    a=Engine._history_group('curves',{'gesture_id':'drag-a','spec':{}})
    b=Engine._history_group('curves',{'gesture_id':'drag-b','spec':{}})
    assert a!=b
    assert a==Engine._history_group('curves',{'gesture_id':'drag-a','spec':{'changed':True}})


def test_repeated_rejection_has_fresh_result_receipts_and_authoritative_recipe():
    from unittest.mock import patch
    e=Engine('curve-receipts');e._guard_editable=lambda who:'export still running'
    events=[]
    with patch('lumaretouch_engine.server.emit',events.append):
        for request in ['request-1','request-2']:
            e.cmd_curves({'action':'set','spec':C.default_curves(),'request_id':request})
    receipts=[v for v in events if v['event']=='curves_result']
    assert [r['request_id'] for r in receipts]==['request-1','request-2']
    assert all(not r['success'] and C.is_identity(r['spec']) for r in receipts)
