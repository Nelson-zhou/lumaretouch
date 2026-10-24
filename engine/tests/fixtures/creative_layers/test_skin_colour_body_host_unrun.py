"""AUTHORED / UNRUN: private body-skin review/publication boundaries.

Synthetic arrays and mocked native/full-export boundaries are not inference,
photographic acceptance, or executed tests. Host and identity contracts only.
"""
from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import skin_colour_body_host as H, full_candidate_render as F
from lumaretouch_engine import skin_colour_body_support as S


def setup(monkeypatch):
    from lumaretouch_engine import people_support_assets as assets, people_algorithms as algorithms
    from lumaretouch_engine import people_resolver as resolver, creative_derived_source as source_module
    from lumaretouch_engine import cpu_memory_budget
    from lumaretouch_engine.skin_colour_state import OP
    source={'sha256':'a'*64,'width':4,'height':4};ref={'face_instance_id':'face'}
    state={'revision':0};candidate={'revision':1};bank={'old':'bytes'};staged_assets={**bank,'new':'review'}
    engine=SimpleNamespace(_people_support=deepcopy(bank),_skin_body_reference={'fence':'fence'})
    target={'scope':'face'};snapshot={'recipe':'unchanged'};row={'path':'original-provenance.png'}
    context={'people_graph':state,'people_support_assets':deepcopy(bank),'other':'untouched'}
    version=SimpleNamespace(document_id='document',revision=7)
    capture=lambda *args:('fence',source,ref,row,snapshot,context,{}, {'observation':'measured'},version)
    monkeypatch.setattr(H,'_capture',capture)
    monkeypatch.setattr(H,'check_action',lambda *args:None)
    monkeypatch.setattr(S,'retain',lambda *args:(deepcopy(candidate),deepcopy(staged_assets)))
    monkeypatch.setattr(assets,'check_store',lambda value:value)
    monkeypatch.setattr(resolver,'resolve',lambda *args:{})
    monkeypatch.setattr(algorithms,'recipes',lambda *args:{OP:{'version':1,'temperature':.3,'tint':0.}})
    monkeypatch.setattr(source_module,'analysis_rgb',lambda _:np.full((4,4,3),128,np.uint8))
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:512*1024*1024)
    monkeypatch.setattr(S,'raster',lambda *args,**kwargs:(np.full((4,4),.5,np.float32),{'measured':True}))
    calls=[]
    def render(e,r,s,document,revision,**kwargs):
        assert e._people_support==bank
        assert r is row and s is snapshot and document=='document' and revision=='7'
        calls.append(deepcopy(kwargs))
        staged=kwargs.get('staged_people_context')
        if staged is not None:
            assert staged['people_graph']==candidate and staged['people_support_assets']==staged_assets
            assert staged['other']=='untouched'
        return np.full((4,4,3),.3 if staged else .2,np.float32),{'exact':'render-proof'}
    monkeypatch.setattr(F,'render',render)
    return engine,state,target,{'review':{'recipe':'reviewed-vectors'}},capture,calls


def test_private_preview_never_swaps_live_support_or_graph(monkeypatch):
    engine,state,target,payload,_,calls=setup(monkeypatch)
    result=H.preview(engine,state,target,payload)
    assert engine._people_support=={'old':'bytes'} and state=={'revision':0}
    assert len(calls)==2 and 'staged_people_context' not in calls[0]
    assert result['before']['mapping']==result['after']['mapping']=='rendered_result'
    assert result['before']['base64']!=result['after']['base64']
    assert result['overlay']['mapping']=='normalized_full_frame'
    assert result['runtime_quality_accepted'] is False
    assert not any(isinstance(value,np.ndarray) for value in engine._skin_body_preview.values())


def test_confirm_appends_only_after_review_fences_and_mark_started(monkeypatch):
    engine,state,target,payload,_,_=setup(monkeypatch)
    result=H.preview(engine,state,target,payload);marks=[]
    candidate,reply=H.confirm(engine,state,target,{'preview_id':result['preview_id'],'reviewed':True},
        mark_started=lambda:marks.append(deepcopy(engine._people_support)))
    assert marks==[{'old':'bytes'}]
    assert candidate=={'revision':1} and reply=={'kind':'confirmed','attached':True}
    assert engine._people_support=={'old':'bytes','new':'review'}
    assert engine._skin_body_preview is None and engine._skin_body_reference is None


@pytest.mark.parametrize('change',['source','body','model','recipe','target','document'])
def test_any_changed_capture_fence_refuses_without_side_effects(monkeypatch,change):
    engine,state,target,payload,capture,_=setup(monkeypatch)
    result=H.preview(engine,state,target,payload);marks=[]
    values=capture();monkeypatch.setattr(H,'_capture',lambda *args:('changed-'+change,*values[1:]))
    with pytest.raises(ValueError):H.confirm(engine,state,target,{'preview_id':result['preview_id'],'reviewed':True},mark_started=lambda:marks.append(True))
    assert marks==[] and engine._people_support=={'old':'bytes'}


def test_changed_private_candidate_bytes_refuse(monkeypatch):
    engine,state,target,payload,_,_=setup(monkeypatch)
    result=H.preview(engine,state,target,payload)
    monkeypatch.setattr(S,'retain',lambda *args:({'revision':1},{'old':'bytes','new':'changed'}))
    with pytest.raises(ValueError):H.confirm(engine,state,target,{'preview_id':result['preview_id'],'reviewed':True})
    assert engine._people_support=={'old':'bytes'}


def test_detach_does_not_require_stale_body_analysis(monkeypatch):
    engine=SimpleNamespace(_skin_body_preview={'old':True},_skin_body_reference={'old':True})
    monkeypatch.setattr(H,'check_action',lambda *args:None)
    monkeypatch.setattr(H,'selected',lambda *args:({}, {'face_instance_id':'face'}))
    monkeypatch.setattr(S,'detach',lambda state,ref:{'revision':2})
    def forbidden(*args):raise AssertionError('Stale body analysis was consulted for detach')
    monkeypatch.setattr(H,'_capture',forbidden)
    candidate,result=H.detach(engine,{'revision':1},{},{})
    assert candidate=={'revision':2} and result['attached'] is False
    assert engine._skin_body_preview is None


def test_display_png_mapping_and_explicit_hdr_refusal():
    source={'sha256':'a'*64,'width':1600,'height':800}
    rgb=np.full((800,1600,3),.5,np.float32)
    overlay=H._png(rgb,source=source);rendered=H._png(rgb)
    assert (overlay['width'],overlay['height'])==(1280,640)
    assert (rendered['width'],rendered['height'])==(960,480)
    assert 'source_width' not in rendered
    with pytest.raises(ValueError):H._png(np.full((4,4,3),1.01,np.float32))
    with pytest.raises(ValueError):H._png(np.full((4,4,3),np.nan,np.float32))


def test_receipt_eviction_preserves_outcome_identity_not_image_replay():
    records=OrderedDict((str(i),{'digest':str(i),'result':{'success':True,'payload':{'kind':'preview','preview_id':str(i)}}}) for i in range(4))
    H.bound_receipt_payloads(records)
    assert all(records[str(i)]['result']['success'] for i in range(4))
    assert all(records[str(i)]['result']['payload_released'] for i in range(2))
    assert all('payload' in records[str(i)]['result'] for i in (2,3))


def identity_fixture(monkeypatch):
    from lumaretouch_engine import virtual_copy_people as V, creative_derived_source as SOURCE
    context={'people_graph':{'revision':0},'people_support_assets':{'old':{'immutable':True}},'other_bank':{'kept':True}}
    row={'path':'original.png','state':{}}
    engine=SimpleNamespace(_creative_base=None,_document_versions=lambda:SimpleNamespace(version=lambda row:SimpleNamespace(document_id='doc',revision=0)))
    monkeypatch.setattr(V,'current_row',lambda _:row)
    monkeypatch.setattr(V,'check',lambda value:deepcopy(value))
    monkeypatch.setattr(F,'people_context',lambda *args:deepcopy(context))
    monkeypatch.setattr(SOURCE,'row_proof',lambda row:{'source':'actual'})
    monkeypatch.setattr(SOURCE,'verify_row',lambda *args:None)
    return engine,row,context


def test_full_candidate_default_identity_schema_remains_compatible(monkeypatch):
    engine,row,context=identity_fixture(monkeypatch)
    proof,_,_=F.identity(engine,row,{},'doc','0')
    assert set(proof)=={'document_id','revision','source_proof','candidate_sha256','people_sha256'}
    from lumaretouch_engine.optics_candidate_identity import fingerprint
    assert proof['people_sha256']==fingerprint({'graph':context['people_graph'],'context':context})


@pytest.mark.parametrize('change',['unrelated','replace_existing','wrong_graph'])
def test_private_context_cannot_replace_unrelated_or_immutable_banks(monkeypatch,change):
    engine,row,context=identity_fixture(monkeypatch);staged=deepcopy(context);graph={'revision':1}
    staged['people_graph']=graph;staged['people_support_assets']['new']={'support':True}
    if change=='unrelated':staged['other_bank']={'kept':False}
    elif change=='replace_existing':staged['people_support_assets']['old']={'immutable':False}
    else:staged['people_graph']={'revision':2}
    with pytest.raises(ValueError):F.identity(engine,row,{},'doc','0',people_graph=graph,staged_people_context=staged)


@pytest.mark.parametrize('fence_changed',[False,True])
def test_prepare_refusal_is_not_unknown_but_publication_fence_change_is(monkeypatch,fence_changed):
    from lumaretouch_engine import people_host_commands as C
    owner=SimpleNamespace(fence=0)
    engine=SimpleNamespace(_people_owner=lambda:owner,_vram=object(),doc_state=lambda:{'current':True})
    raw={'cmd':'people','document_id':'doc','document_epoch':'epoch','document_revision':0,
         'state_revision':0,'association_revision':0,'request_id':'confirm-request',
         'target':{'scope':'face'},'action':'skin_body_confirm','payload':{'preview_id':'preview','reviewed':True}}
    monkeypatch.setattr(C,'checked',lambda *args:({}, {'asset_sha256':'a'*64},raw['target']))
    def confirm(*args,mark_started):
        mark_started();engine._people_support={'unused':'append-only'}
        return {'candidate':True},{'kind':'confirmed','attached':True}
    monkeypatch.setattr(H,'confirm',confirm)
    def publish(*args,**kwargs):
        if fence_changed:owner.fence=1
        raise ValueError('fixture publication refusal')
    monkeypatch.setattr(C,'publish',publish)
    with pytest.raises(ValueError):C.apply(engine,raw,lambda _:None)
    replies=[];C.finish(engine,raw,'fixture publication refusal',replies.append)
    assert replies[0]['success'] is False
    assert replies[0]['outcome_unknown'] is fence_changed
    # Exact receipt replay does not re-run confirmation or publication.
    monkeypatch.setattr(H,'confirm',lambda *a,**k:pytest.fail('replayed mutation'))
    C.apply(engine,raw,lambda _:None);C.finish(engine,raw,None,replies.append)
    assert replies[1]==replies[0]
