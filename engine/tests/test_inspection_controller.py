"""Controller owns lifecycle without depending on Engine or its reader thread."""
import pytest
from lumaretouch_engine.inspection_controller import InspectionController


def controller(*, busy=False):
    events=[]; dimensions=[]
    c=InspectionController(document=lambda:'/fixture.png',
        proxy_dimensions=lambda:(dimensions.append('read') or (64,96)),
        busy=lambda:busy,capture_snapshot=lambda:{},emit=events.append)
    return c,events,dimensions


def test_busy_rejection_does_not_read_dimensions_or_replace_prior_identity():
    c,events,dimensions=controller(busy=True)
    c.request_id='7';c.last_id=7
    with pytest.raises(ValueError,match='busy'):
        c.handle_command({'action':'start','request_id':'8','max_asset_bytes':1024})
    assert dimensions==[] and c.request_id=='7' and c.last_id==7
    assert events[-1]['request_id']=='8' and events[-1]['rejected'] is True


def test_stale_start_rejection_does_not_capture_dimensions():
    c,events,dimensions=controller();c.request_id='7';c.last_id=7
    with pytest.raises(ValueError,match='increase'):
        c.handle_command({'action':'start','request_id':'7','max_asset_bytes':1024})
    assert dimensions==[] and c.request_id=='7'


def test_status_and_wrong_cancel_have_no_hidden_engine_dependency():
    c,events,_=controller();c.request_id='1'
    c.handle_command({'action':'status'})
    assert events[-1]['request_id']=='1' and events[-1]['state']=='idle'
    with pytest.raises(ValueError,match='identity'):
        c.handle_command({'action':'cancel','request_id':'2'})
    c.handle_command({'action':'cancel','request_id':'1'})
    assert events[-1]['state']=='cancelled' and not c.worker_running
    c.shutdown()
