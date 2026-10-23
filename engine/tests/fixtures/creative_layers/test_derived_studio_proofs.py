"""AUTHORED / UNRUN: studio source fences, not model/visual acceptance.

These cases intentionally do not establish full-resolution model inference,
OpenCV quality, Rust replay, GPU rendering, export codecs or product acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_studio as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_derived_repair_runtime as R
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import studio_background_state as S


SOURCE={'sha256':'1'*64,'width':8,'height':6}
MODEL={'backend':'mediapipe','contract':M.SEMANTIC_CONTRACT+':'+'4'*64}
STAMP=(1,2,3,4,5)


def recipe(*,semantic=False,active=True,strokes=False):
    value=S.empty();value['source']=deepcopy(SOURCE)
    if active:value['parameters']['enhancement']=.4
    if semantic:
        value['region_mode']='semantic_background';value['semantic_owner']=deepcopy(MODEL)
    if strokes:
        value['strokes']=[{'id':'retained','target':'recover_uniformity','operation':'add',
            'axes':[[.05,0.],[0.,.05]],'points':[[.5,.5,1.]],'feather':.4,'flow':.7,'opacity':.8}]
    return value


def context(*,semantic=False,active=True,strokes=False):
    value=recipe(semantic=semantic,active=active,strokes=strokes)
    mask=np.arange(12,dtype=np.float32).reshape(3,4)/11 if semantic else None
    return {'version':1,'source':deepcopy(SOURCE),'original_sha256':'2'*64,
        'recipe':value,'recipe_sha256':C.recipe_digest(value),
        'analysis':{**SOURCE,'proxy_width':4,'proxy_height':3,'proxy_sha256':'3'*64} if semantic else None,
        'semantic_owner':deepcopy(MODEL) if semantic else None,
        'mask':mask,'mask_sha256':C._hash(mask) if semantic else None}


def bind_source(monkeypatch):
    monkeypatch.setattr(D,'record',lambda owner:object())
    monkeypatch.setattr(D,'binding',lambda owner:deepcopy(SOURCE))


def test_inactive_regions_recovery_and_brightness_still_own_the_source(monkeypatch):
    bind_source(monkeypatch)
    value=recipe(active=False,strokes=True)
    assert not S.active(value)
    assert C.validate_state({'creative_base':object(),'studio_background':value})==value
    value['source']['sha256']='5'*64
    with pytest.raises(ValueError):C.validate(value,SOURCE)
    value=recipe(active=False);value['parameters']['brightness']=20
    value['source']['width']+=1
    with pytest.raises(ValueError):C.validate(value,SOURCE)


def test_ambiguous_aliases_cannot_hide_foreign_or_disabled_intent(monkeypatch):
    bind_source(monkeypatch)
    for value in (
        {'creative_base':object(),'studio_background':S.empty(),'_studio_background':recipe(active=False,strokes=True)},
        {'creative_base':object(),'_creative_base':None,'studio_background':S.empty()},
    ):
        with pytest.raises(ValueError):C.validate_state(value)


def test_exact_recipe_and_semantic_evidence_are_frozen():
    value=context(semantic=True,active=False,strokes=True)
    assert C.verify_context(value,SOURCE) is value
    changes=(
        lambda c:c['recipe']['strokes'][0]['points'][0].__setitem__(0,.6),
        lambda c:c['mask'].__setitem__((0,0),.2),
        lambda c:c['analysis'].__setitem__('sha256','5'*64),
        lambda c:c['semantic_owner'].__setitem__('contract',M.SEMANTIC_CONTRACT+':'+'5'*64),
        lambda c:c.__setitem__('version',True),
    )
    for change in changes:
        bad=deepcopy(value);change(bad)
        with pytest.raises(ValueError):C.verify_context(bad,SOURCE)
    with pytest.raises(ValueError):C.verify_context(value,{**SOURCE,'sha256':'5'*64})


def test_manual_context_cannot_keep_hidden_model_or_mask():
    value=context();assert C.verify_context(value,SOURCE) is value
    for key,bad in (('mask',np.ones((3,4),np.float32)),('semantic_owner',MODEL),
                    ('analysis',{'anything':'unowned'}),('mask_sha256','a'*64)):
        changed=deepcopy(value);changed[key]=bad
        with pytest.raises(ValueError):C.verify_context(changed,SOURCE)


def test_snapshot_requires_exact_bound_intent_and_full_source_extent(monkeypatch):
    bind_source(monkeypatch);value=context(active=False,strokes=True)
    snap={'creative_base':object(),'studio_background':value['recipe'],'creative_studio_context':value}
    assert C.verify_snapshot(snap,shape=(6,8)) is value
    with pytest.raises(ValueError):C.verify_snapshot(snap,shape=(3,4))
    snap['studio_background']=deepcopy(value['recipe']);snap['studio_background']['parameters']['enhancement']=.7
    with pytest.raises(ValueError):C.verify_snapshot(snap)
    snap={'creative_base':object(),'studio_background':recipe(active=False,strokes=True)}
    with pytest.raises(ValueError):C.verify_snapshot(snap)


def test_unbound_neutral_needs_no_model_and_rejects_hidden_context(monkeypatch):
    bind_source(monkeypatch)
    assert C.capture({'creative_base':object(),'studio_background':S.empty()}) is None
    assert C.verify_snapshot({'creative_base':object(),'studio_background':S.empty()}) is None
    with pytest.raises(ValueError):
        C.verify_snapshot({'creative_base':object(),'studio_background':S.empty(),'creative_studio_context':context()})
    monkeypatch.setattr(D,'record',lambda owner:None)
    with pytest.raises(ValueError):C.verify_snapshot({'studio_background':S.empty(),'creative_studio_context':context()})


def test_physical_original_provenance_is_not_the_effective_source(monkeypatch):
    value=context()
    monkeypatch.setattr(M,'source_digest',lambda path:'2'*64)
    assert C.verify_context(value,SOURCE,path='physical-original') is value
    monkeypatch.setattr(M,'source_digest',lambda path:SOURCE['sha256'])
    with pytest.raises(ValueError):C.verify_context(value,SOURCE,path='physical-original')


class Tensor:
    """Only the read-only tensor adapter needed by owned input verification."""
    def __init__(self,array):self.array=array
    def __getitem__(self,index):return Tensor(self.array[index])
    def permute(self,*axes):return Tensor(self.array.transpose(axes))
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.array


def live(monkeypatch,*,semantic=False,active=True,repaired=True):
    bind_source(monkeypatch)
    proxy=np.full((3,4,3),102,np.uint8);pixels=proxy.astype(np.float32)/255.
    tensor=lambda rgb:Tensor(rgb.transpose(2,0,1)[None].copy())
    pipe=SimpleNamespace(h=3,w=4,src_f32=tensor(pixels),repair_base=tensor(pixels+.1) if repaired else None,
        repair_ops=[],redo_ops=[],_creative_repair_source=deepcopy(SOURCE),has_background=lambda:False)
    stack=REPAIRS.digest_ops([],[],SOURCE)
    pipe._creative_repair_evidence=R.make_evidence(SOURCE,pixels,pixels+.1 if repaired else None,stack)
    pipe._creative_repair_input=deepcopy(pipe._creative_repair_evidence['input'])
    proof={**SOURCE,'proxy_width':4,'proxy_height':3,'proxy_sha256':C._hash(proxy)}
    pc=SimpleNamespace(backend='mediapipe',semantic_model_sha256='4'*64,input_source_binding=proof,
        masks={'background':np.full((3,4),.75,np.float32)}) if semantic else None
    engine=SimpleNamespace(_vram=pipe,_precompute=pc,_precompute_backend='mediapipe',
        _doc_path='physical-original',_docs=[{'path':'physical-original','_local_source_stamp':STAMP}],
        _doc_index=0,_studio_background=recipe(semantic=semantic,active=active),_repair_ops=[],_redo_ops=[])
    monkeypatch.setattr(D,'analysis_rgb',lambda owner:proxy)
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    monkeypatch.setattr(M,'source_digest',lambda path:'2'*64)
    return engine,proxy,pixels


def test_preview_measures_owned_pre_repair_pixels_not_repaired_base(monkeypatch):
    engine,_,pixels=live(monkeypatch)
    frozen,actual,key=C.preview(engine)
    np.testing.assert_array_equal(actual,pixels)
    assert not np.array_equal(actual,engine._vram.repair_base[0].permute(1,2,0).numpy())
    assert frozen['source']==SOURCE and frozen['original_sha256']!='1'*64
    assert C.key(engine,engine._studio_background)==key
    assert C.semantic(engine,engine._studio_background) is None
    context_none,neutral_pixels,neutral_key=C.preview(engine,S.empty())
    assert context_none is None and neutral_key!=key
    np.testing.assert_array_equal(neutral_pixels,pixels)


def test_preview_rejects_changed_actual_input_output_and_analysis_rgb(monkeypatch):
    for target in ('input','output','analysis'):
        engine,proxy,_=live(monkeypatch)
        if target=='input':engine._vram.src_f32.array[0,0,0,0]+=.01
        elif target=='output':engine._vram.repair_base.array[0,0,0,0]+=.01
        else:proxy[0,0,0]+=1
        with pytest.raises(ValueError):C.preview(engine)


def test_live_semantic_capture_owns_current_model_input_and_actual_field(monkeypatch):
    engine,_,_=live(monkeypatch,semantic=True)
    frozen,_,key=C.preview(engine)
    assert frozen['mask'].flags.writeable is False
    engine._precompute.masks['background'][0,0]=.5
    assert C.key(engine,engine._studio_background)!=key
    assert frozen['mask'][0,0]==.75
    engine._precompute.input_source_binding['proxy_sha256']='7'*64
    with pytest.raises(ValueError):C.preview(engine)
    engine,_,_=live(monkeypatch,semantic=True)
    engine._precompute.semantic_model_sha256='5'*64
    with pytest.raises(ValueError):C.preview(engine)


def test_disabled_retained_semantic_intent_needs_analysis_not_silhouette_fallback(monkeypatch):
    engine,_,_=live(monkeypatch,semantic=True,active=False)
    assert C.capture(engine)['mask'] is not None
    engine._precompute=None
    with pytest.raises(ValueError):C.capture(engine)
    engine,_,_=live(monkeypatch,semantic=True)
    engine._precompute.masks={'person':np.ones((3,4),np.float32)}
    with pytest.raises(ValueError):C.preview(engine)


def test_export_needs_canonical_full_float_not_proxy_repair_or_quantization(monkeypatch):
    bind_source(monkeypatch);value=context(semantic=True)
    spec=SimpleNamespace(creative_base=object(),creative_studio_context=value,studio_background=value['recipe'])
    pixels=np.full((6,8,3),.400001,np.float32)
    with pytest.raises(ValueError):C.verify_export(spec,pixels)
    C.stamp_pixels(spec,pixels)
    assert C.verify_export(spec,pixels) is value
    for bad in (pixels+.1,pixels[:3,:4],np.round(pixels*255).astype(np.uint8),pixels.astype(np.float64)):
        with pytest.raises(ValueError):C.verify_export(spec,bad)
    for divisor in (255.,65535.,True):
        with pytest.raises(ValueError):C.verify_export(spec,pixels,divisor)
    spec.studio_background=deepcopy(value['recipe']);spec.studio_background['parameters']['enhancement']=.7
    with pytest.raises(ValueError):C.verify_export(spec,pixels)


@pytest.mark.parametrize('bad',[np.nan,np.inf,-.01,1.01])
def test_export_refuses_hdr_nonfinite_instead_of_clipping(monkeypatch,bad):
    bind_source(monkeypatch);value=context()
    spec=SimpleNamespace(creative_base=object(),creative_studio_context=value,studio_background=value['recipe'])
    pixels=np.full((6,8,3),.4,np.float32);pixels[0,0,0]=bad
    with pytest.raises(ValueError):C.stamp_pixels(spec,pixels)
