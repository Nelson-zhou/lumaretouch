"""AUTHORED / UNRUN: source contracts only, not native mask or visual acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_effects_contract import fixture
from lumaretouch_engine import creative_derived_masks as D,creative_derived_source as SOURCE
from lumaretouch_engine import local_mask_state as M,local_grade_runtime as G,local_grade_source as GS


def setup(monkeypatch,tmp_path,semantic=False):
    engine,_,_,source,rgb=fixture(monkeypatch)
    path=tmp_path/'original.bin';path.write_bytes(b'physical-original-not-composite')
    engine._doc_path=str(path);engine._precompute_backend='mediapipe'
    engine._precompute.semantic_model_sha256='2'*64
    obj={'id':'mask','name':'review','enabled':True,'operation':'add','kind':'semantic' if semantic else 'luminance_range','opacity':1.,'feather':0.}
    if semantic:obj['channel']='skin'
    else:obj.update(low=.2,high=.8)
    mask={'recipe':{'version':1,'domain':'source-normalized','objects':[obj]},'source':source,
          'semantic_owner':M.current_owner(engine) if semantic else None}
    return engine,source,rgb,mask,str(path)


def test_capture_owns_effective_source_and_exact_semantics(monkeypatch,tmp_path):
    engine,source,_,mask,path=setup(monkeypatch,tmp_path,True)
    context=D.capture(engine,[mask])
    assert context['source']==source and context['original_sha256']==M.source_digest(path)
    assert context['source']['sha256']!=context['original_sha256']
    assert not context['fields']['skin'].flags.writeable
    assert context['fields']['skin'] is not engine._precompute.masks['skin']
    D.verify_context(context,source,[mask],path)
    mutated=deepcopy(context);mutated['fields']['skin']=np.array(mutated['fields']['skin'],copy=True);mutated['fields']['skin'][0,0]=.5
    with pytest.raises(ValueError,match='coverage'):D.verify_context(mutated,source,[mask])
    mutated=deepcopy(context);mutated['analysis']['sha256']='f'*64
    with pytest.raises(ValueError):D.verify_context(mutated,source,[mask])


def test_disabled_foreign_group_is_never_ignored(monkeypatch,tmp_path):
    engine,source,_,mask,_=setup(monkeypatch,tmp_path)
    bad=deepcopy(mask);bad['source']['sha256']='f'*64;bad['recipe']['objects'][0]['enabled']=False
    groups={'version':1,'layers':[{'id':'g','name':'g','enabled':False,'grade':[0,0,0,1],'mask':bad}]}
    with pytest.raises(ValueError):D.live_dependencies(engine,groups)
    with pytest.raises(ValueError):D.capture(engine,[bad])


def test_missing_or_original_precompute_cannot_feed_derived_semantics(monkeypatch,tmp_path):
    engine,source,_,mask,_=setup(monkeypatch,tmp_path,True)
    engine._precompute.input_source_binding=None
    with pytest.raises(ValueError):D.capture(engine,[mask])
    engine._precompute=None
    with pytest.raises(ValueError):D.capture(engine,[mask])


def test_live_dependencies_detect_field_mutation_without_copy(monkeypatch,tmp_path):
    engine,source,_,mask,_=setup(monkeypatch,tmp_path,True)
    groups={'version':1,'layers':[{'id':'g','name':'g','enabled':True,'grade':[.1,0,0,1],'mask':mask}]}
    first=D.live_dependencies(engine,groups)
    engine._precompute.masks['skin'][0,0]=.5
    second=D.live_dependencies(engine,groups)
    assert first['field_sha256']!=second['field_sha256']
    assert first['source']==second['source']==source


def test_snapshot_checks_provenance_and_canonical_extent(monkeypatch,tmp_path):
    engine,source,_,mask,path=setup(monkeypatch,tmp_path)
    snap={'creative_base':engine._creative_base,'grade_scope':'objects','local_masks':mask,
          'creative_mask_context':D.capture(engine,[mask])}
    M.verify_snapshot(snap,path,(4,4))
    with pytest.raises(ValueError):M.verify_snapshot(snap,path,(8,8))
    (tmp_path/'original.bin').write_bytes(b'changed')
    with pytest.raises(ValueError):M.verify_snapshot(snap,path,(4,4))


def test_primitive_export_uses_actual_float_source_and_never_original_resolver(monkeypatch,tmp_path):
    engine,source,_,mask,_=setup(monkeypatch,tmp_path)
    pixels=np.full((4,4,3),.123456,np.float32);calls=[]
    spec=SimpleNamespace(creative_base=engine._creative_base,creative_mask_context=D.capture(engine,[mask]),
        grade_scope='objects',local_masks=mask)
    monkeypatch.setattr(M.R,'raster',lambda stack,shape,**kw: calls.append(kw) or np.ones(shape,np.uint8))
    with pytest.raises(ValueError):M.export_prepare(spec,pixels)
    D.stamp_pixels(spec,pixels);M.export_prepare(spec,pixels)
    assert calls[0]['rgb'] is pixels and calls[0]['semantic']=={}
    changed=pixels.copy();changed[0,0,0]=.3
    with pytest.raises(ValueError):M.export_prepare(spec,changed)


def test_derived_group_raster_never_calls_file_semantic_inference(monkeypatch,tmp_path):
    engine,source,_,mask,path=setup(monkeypatch,tmp_path,True)
    context=D.capture(engine,[mask]);groups={'version':1,'layers':[{'id':'g','name':'g','enabled':True,'grade':[.1,0,0,1],'mask':mask}]}
    def forbidden(*a,**k):raise AssertionError('Physical original inference attempted')
    monkeypatch.setattr(G.S,'fields',forbidden);monkeypatch.setattr(M,'verify_source',forbidden)
    monkeypatch.setattr(M.R,'raster',lambda stack,shape,**kw:np.ones(shape,np.uint8))
    assert len(G.rasters(groups,path,(4,4),rgb=np.zeros((4,4,3),np.float32),creative_context=context,engine=engine))==1
    snap={'creative_base':engine._creative_base,'local_grade_groups':groups,'creative_mask_context':context}
    GS.verify_snapshot(snap,path,(4,4))


def test_disabled_group_keeps_ownership_without_forcing_semantic_reanalysis(monkeypatch,tmp_path):
    engine,source,_,mask,path=setup(monkeypatch,tmp_path,True)
    engine._precompute=None
    groups={'version':1,'layers':[{'id':'g','name':'g','enabled':False,'grade':[.1,0,0,1],'mask':mask}]}
    snap={'creative_base':engine._creative_base,'local_grade_groups':groups}
    all_masks=D.masks(snap);active=D.masks(snap,active_only=True)
    assert all_masks and not active
    snap['creative_mask_context']=D.capture(engine,all_masks,active_values=active)
    D.verify_snapshot(snap,path)
    assert snap['creative_mask_context']['fields']=={}
    with pytest.raises(ValueError):D.capture(engine,all_masks)  # explicit inspection still needs real category evidence


def test_legacy_sync_cache_validates_pixels_before_reusing_raster(monkeypatch,tmp_path):
    import torch
    engine,source,rgb,mask,path=setup(monkeypatch,tmp_path)
    calls=[]
    pipe=SimpleNamespace(src_f32=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float()/255.,h=4,w=4,
        local_mask_suspended=None,grade_scope='objects')
    def install(weight,reason=None):pipe.local_mask_suspended=reason;calls.append(('install',reason))
    pipe.set_local_mask=install;engine._vram=pipe;engine._local_masks=mask;engine._grade_scope='objects'
    engine._docs=[{'path':path,'_local_source_stamp':M.file_stamp(path)}];engine._doc_index=0
    monkeypatch.setattr(M.R,'raster',lambda *a,**kw:calls.append(('raster',None)) or np.ones((4,4),np.uint8))
    M.sync(engine,strict=True);M.sync(engine,strict=True)
    assert [kind for kind,_ in calls].count('raster')==1
    pipe.src_f32[0,0,0,0]=.25
    with pytest.raises(ValueError,match='pixels'):M.sync(engine,strict=True)
    assert pipe.local_mask_suspended and [kind for kind,_ in calls].count('raster')==1


def test_group_sync_cache_checks_semantic_hash_and_strict_suspension(monkeypatch,tmp_path):
    import torch
    engine,source,rgb,mask,path=setup(monkeypatch,tmp_path,True);calls=[]
    store=SimpleNamespace(suspended=None)
    def install(fields,reason=None):store.suspended=reason
    store.set=install
    pipe=SimpleNamespace(src_f32=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float()/255.,h=4,w=4,local_grade_layers=store)
    engine._vram=pipe;engine._docs=[{'path':path,'_local_source_stamp':M.file_stamp(path)}];engine._doc_index=0
    engine._local_grade_layers={'version':1,'layers':[{'id':'g','name':'g','enabled':True,'grade':[.1,0,0,1],'mask':mask}]}
    monkeypatch.setattr(M.R,'raster',lambda *a,**kw:calls.append(kw) or np.ones((4,4),np.uint8))
    G.sync(engine,strict=True);G.sync(engine,strict=True)
    assert len(calls)==1
    engine._precompute.masks['skin'][0,0]=.5
    G.sync(engine,strict=True);assert len(calls)==2
    store.suspended='retained refusal'
    with pytest.raises(ValueError,match='retained refusal'):G.sync(engine,strict=True)


def test_original_bind_source_still_hashes_physical_file(monkeypatch,tmp_path):
    engine,source,_,_,path=setup(monkeypatch,tmp_path)
    engine._docs=[{'path':path,'_local_source_stamp':M.file_stamp(path),'src_w':4,'src_h':4}];engine._doc_index=0
    assert M.bind_source(engine)['sha256']==M.source_digest(path)!=source['sha256']
