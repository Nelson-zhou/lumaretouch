from types import SimpleNamespace
import pytest
from lumaretouch_engine import color_capture_pipeline as capture


def test_presentation_geometry_is_distinct_from_fixed_proxy_raster():
    shm=SimpleNamespace(w=1200,h=800,instance_id=bytes([1])*16)
    context=capture.document_context('123',shm,{'out_full':[4000,4000],'out':[800,800]})
    assert (context['width'],context['height'])==(1200,800)
    assert (context['presentation_width'],context['presentation_height'])==(4000,4000)


def test_sample_extracts_float_output_neighbourhood_without_pack_or_frame_write(monkeypatch):
    torch=pytest.importorskip('torch')
    pixels=torch.arange(3*4*5,dtype=torch.float32).reshape(1,3,4,5)/100
    class Pipeline:
        w=5;h=4
        def retouch(self,strength,channel,scope_tap,**params):
            assert strength==.25 and channel=='test' and params=={'example':True}
            scope_tap('levels-input',pixels*0);scope_tap('output',pixels)
        def pack(self,*a,**k):raise AssertionError('sampling must not publish a new frame')
    seen=[]
    monkeypatch.setattr(capture,'analyze',lambda sample:(seen.append(sample) or {'samples':sample.width*sample.height}))
    assert capture.sample_output(Pipeline(),.25,'test',{'example':True},{'x':3,'y':2,'width':2,'height':2},(5,4))=={'samples':4}
    expected=pixels[0,:,2:4,3:5].permute(1,2,0).numpy()
    assert (seen[0].pixels==expected).all()
    with pytest.raises(ValueError):capture.sample_output(Pipeline(),.25,'test',{}, {'x':4,'y':0,'width':2,'height':1},(5,4))


def test_capture_dispatch_is_read_only_and_other_commands_invalidate_before_execution(monkeypatch):
    import json
    from lumaretouch_engine import server
    engine=server.Engine('capture-dispatch');events=[];calls=[]
    monkeypatch.setattr(server,'emit',events.append)
    def forbidden(*a,**k):raise AssertionError('capture must not cancel inspection or write history')
    monkeypatch.setattr(engine,'_cancel_snapshot',forbidden)
    monkeypatch.setattr(engine,'_history_capture',forbidden)
    engine._process_line(json.dumps({'cmd':'color_capture','action':'arm'}),{'color_capture':lambda p:calls.append(p)})
    assert len(calls)==1 and not events
    owner=engine._color_capture_controller();generation=owner.generation
    monkeypatch.setattr(engine,'_cancel_snapshot',lambda *a:None)
    def mutate(p):assert owner.generation==generation+1
    engine._process_line(json.dumps({'cmd':'example_mutation'}),{'example_mutation':mutate})
    assert owner.generation==generation+1 and not events


def test_capture_guard_preserves_inspection_resource_ownership(monkeypatch):
    from lumaretouch_engine import server
    engine=server.Engine('capture-busy');events=[];lease=object()
    owner=SimpleNamespace(tx=lease,result=None,job=None)
    monkeypatch.setattr(server,'emit',events.append)
    monkeypatch.setattr(engine,'_inspection_controller',lambda:owner)
    monkeypatch.setattr(engine,'_guard_editable',lambda name:None)
    engine.cmd_color_capture({'cmd':'color_capture','action':'arm','capture_id':'1'*32,'ticket':'1','document_id':'123'})
    assert owner.tx is lease and not events[-1]['success']
    assert 'inspection' in events[-1]['error'].lower()
