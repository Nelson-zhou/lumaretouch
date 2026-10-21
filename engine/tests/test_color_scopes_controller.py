import json
from types import SimpleNamespace
from lumaretouch_engine.color_scopes_controller import ScopePorts,handle_scopes


def request(**extra):
    return dict(cmd='color_scopes',request_id='request',document_id='photo',stage='output',ticket='1',**extra)


def fixture(reason=None):
    events=[];calls=[]
    sample=SimpleNamespace(width=1000,height=2000,grid_width=128,grid_height=256)
    ports=ScopePorts(lambda:'photo',lambda:reason,lambda stage:(calls.append(stage) or sample),lambda s:{'samples':32768})
    return ports,events,calls


def test_result_identifies_stage_sampling_and_whitepoint_without_claiming_full_source():
    ports,events,calls=fixture();handle_scopes(request(),ports,events.append)
    r=events[-1];assert r['success'] and calls==['output'] and r['ticket']=='1'
    assert r['eligible_pixels']==2000000 and r['sampled_pixels']==32768
    assert r['quality']=='sampled-proxy-float' and r['lab_whitepoint']=='D65'


def test_stale_document_invalid_fields_and_inspection_busy_do_not_sample():
    for patch in [{'document_id':'old'},{'stage':'fake'},{'ticket':'-1'},{'unknown':1}]:
        ports,events,calls=fixture();p=request();p.update(patch);handle_scopes(p,ports,events.append)
        assert not calls and not events[-1]['success']
    ports,events,calls=fixture('inspection owns a lease');handle_scopes(request(),ports,events.append)
    assert not calls and events[-1]['error']=='inspection owns a lease'


def test_read_only_dispatch_does_not_cancel_inspection_or_touch_history(monkeypatch):
    from lumaretouch_engine import server
    e=server.Engine('scopes-dispatch');events=[];called=[]
    monkeypatch.setattr(server,'emit',events.append)
    def forbidden(*a,**k):raise AssertionError('read-only scopes must not cancel or capture history')
    monkeypatch.setattr(e,'_cancel_snapshot',forbidden)
    monkeypatch.setattr(e,'_history_capture',forbidden)
    e._process_line(json.dumps(request()),{'color_scopes':lambda p:called.append(p)})
    assert len(called)==1 and not events


def test_engine_scope_guard_defers_before_render_arguments_and_preserves_lease(monkeypatch):
    from lumaretouch_engine import server
    e=server.Engine('scopes-busy');e._load_id='photo';events=[]
    lease=object();owner=SimpleNamespace(tx=lease,result=None,job=None)
    monkeypatch.setattr(server,'emit',events.append)
    monkeypatch.setattr(e,'_inspection_controller',lambda:owner)
    monkeypatch.setattr(e,'_guard_editable',lambda name:None)
    def forbidden():raise AssertionError('render arguments must not be read while inspection owns memory')
    monkeypatch.setattr(e,'_retouch_render_args',forbidden)
    e.cmd_color_scopes(request())
    assert owner.tx is lease and events[-1]['event']=='color_scopes' and not events[-1]['success']
    assert 'inspection owns resources' in events[-1]['error']
