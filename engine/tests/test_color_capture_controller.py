from copy import deepcopy
from dataclasses import replace
from lumaretouch_engine.color_capture_controller import CapturePorts,ColorCaptureController

CID='0123456789abcdef0123456789abcdef'

def fixture():
    document={'document_id':'123','shm_instance':'f'*32,'width':80,'height':64,'presentation_width':1,'presentation_height':1}
    events=[];samples=[]
    ports=CapturePorts(lambda:document,lambda:None,lambda:{'event':'frame','w':80,'h':64,'seq':7},
        lambda region,dims:(samples.append((deepcopy(region),dims)) or {'mean_srgb':[.1,.2,.3]}))
    return ColorCaptureController(ports,events.append),document,events,samples

def arm(**extra):return dict(action='arm',capture_id=CID,ticket='1',document_id='123',**extra)

def sample(c,**extra):
    p=dict(action='sample',capture_id=CID,ticket='1',document_id='123',generation=str(c.generation),
           request_id='point',request_ticket='2',x=0,y=0,size=3)
    p.update(extra);return p


def test_capture_is_producer_bound_and_neighbourhood_clips_to_image_not_outside_click():
    c,doc,events,samples=fixture();c.handle(arm());assert events[-1]['success']
    assert events[-2]['event']=='frame' and c.capture['seq']=='7'
    assert c.capture['presentation_width']==1 and c.capture['width']==80
    c.handle(sample(c));assert events[-1]['success']
    assert samples==[({'x':0,'y':0,'width':2,'height':2},(80,64))]
    c.handle(sample(c,x=-1));assert not events[-1]['success'] and len(samples)==1


def test_edits_cancel_stale_samples_even_when_document_and_mapping_unchanged():
    c,doc,events,samples=fixture();c.handle(arm());request=sample(c)
    c.invalidate();c.handle(request);assert not events[-1]['success'] and samples==[]
    c.handle(arm());c.handle(request);assert not events[-1]['success'] and samples==[]


def test_old_cancel_cannot_clear_new_ticket():
    c,doc,events,_=fixture();c.handle(arm())
    newer=arm();newer['ticket']='2';c.handle(newer)
    c.handle({'action':'cancel','capture_id':CID,'ticket':'1','document_id':'123'})
    assert not events[-1]['success'] and c.capture['ticket']=='2'


def test_guard_and_geometry_change_reject_without_publishing_capture():
    c,doc,events,_=fixture();c.ports=replace(c.ports,guard=lambda:'inspection owns memory')
    c.handle(arm());assert not events[-1]['success'] and c.capture is None
    c,doc,events,_=fixture()
    def render():doc['presentation_width']=2;return {'event':'frame','w':80,'h':64,'seq':7}
    c.ports=replace(c.ports,render=render);c.handle(arm())
    assert not events[-1]['success'] and c.capture is None and len(events)==1


def test_invalidation_during_sample_discards_computed_values():
    c,doc,events,_=fixture();c.handle(arm())
    def compute(region,dims):c.invalidate();return {'mean_srgb':[1,1,1]}
    c.ports=replace(c.ports,sample=compute);c.handle(sample(c))
    assert not events[-1]['success'] and 'analysis' not in events[-1]


def test_invalidation_while_rendering_does_not_grant_a_new_identity_to_old_pixels():
    c,doc,events,_=fixture()
    def render():c.invalidate();return {'event':'frame','w':80,'h':64,'seq':7}
    c.ports=replace(c.ports,render=render);c.handle(arm())
    assert c.capture is None and len(events)==1 and not events[-1]['success']
