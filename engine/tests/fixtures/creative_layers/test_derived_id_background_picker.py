"""AUTHORED / UNRUN: ID picker source/lease fences, not visual acceptance.

The synthetic target proof and raster owners below isolate picker routing. They
do not establish canonical decoding, real SAM inference, native presentation,
GPU rendering, export quality, or photographic/product acceptance.
"""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import id_background_picker as C
from lumaretouch_engine import id_background_state as S
from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_derived_id_background as B
from lumaretouch_engine import reference_color_assets as A
from lumaretouch_engine import sample_library_controller as LIB
from lumaretouch_engine import local_mask_state as M


SOURCE={'sha256':'1'*64,'width':8,'height':6}
REFERENCE_SOURCE={'sha256':'2'*64,'width':64,'height':64}
ACTIONS={'original':'id_background','subject':'id_background_subject','reference':'id_background_reference'}


def reviewed(category='contact'):
    obj={'id':'reviewed-contact','name':'Independent manual contact review','enabled':True,
         'operation':'add','kind':'luminance_range','opacity':1.,'feather':0.,'low':.1,'high':.9}
    mask={'source':deepcopy(SOURCE),'semantic_owner':None,
          'recipe':{'version':1,'domain':'source-normalized','objects':[obj]}}
    return U.check_binding({'version':1,'category':category,'reviewed':True,
                           'mask':mask,'recipe_sha256':U.digest(mask)},category)


def rig(monkeypatch,tmp_path):
    torch=pytest.importorskip('torch')
    rgb=np.broadcast_to(np.array([.1251,.2502,.5003],np.float32),(3,4,3)).copy()
    pipe=SimpleNamespace(w=4,h=3,device=torch.device('cpu'),crop_rect=(0.,0.,1.,1.),crop_rotation=0.,
        src_f32=torch.from_numpy(rgb.transpose(2,0,1).copy())[None],
        repair_base=torch.full((1,3,3,4),.8,dtype=torch.float32))
    value=S.empty();value['source']=deepcopy(SOURCE);value['support']['contact']=reviewed()
    engine=SimpleNamespace(_vram=pipe,_id_background=value,_doc_path='original-provenance-only',
        _src_rgb=np.full((3,4,3),245,np.uint8),_load_id=7,revision=9,review_key='owned-review-v1')
    pinned=C._array_proof(rgb,3);preview_calls=[]
    def preview(owner,value=None):
        current=owner._vram.src_f32[0].permute(1,2,0).detach().cpu().numpy()
        if C._array_proof(current,3)!=pinned:raise ValueError('Actual canonical source proxy changed')
        preview_calls.append(deepcopy(value))
        return {'source':deepcopy(SOURCE)},current,(owner.review_key,C._digest(value),pinned)
    monkeypatch.setattr(D,'record',lambda owner:object())
    monkeypatch.setattr(D,'binding',lambda owner:deepcopy(SOURCE))
    monkeypatch.setattr(B,'preview',preview)
    def original_forbidden(*args,**kwargs):raise AssertionError('Derived picker read original pixels/path')
    monkeypatch.setattr(M,'bind_source',original_forbidden)
    monkeypatch.setattr(M,'verify_source',original_forbidden)
    alpha=np.zeros((3,4),np.float32);alpha[1,1]=1.;alpha[1,2]=.999
    raster_calls=[]
    def raster(binding,path,source,**kwargs):
        assert binding['category']=='contact' and path is None
        assert kwargs['effective_source']==SOURCE
        raster_calls.append((binding,path,source.copy(),kwargs))
        return alpha.copy()
    monkeypatch.setattr(U,'raster',raster)
    monkeypatch.setattr(C,'available_estimate',lambda:16*1024**3)
    monkeypatch.setattr(C,'available_memory',lambda device:16*1024**3)
    capture_root=tmp_path/'captures';capture_root.mkdir(mode=0o700)
    monkeypatch.setenv('LRT_INSPECTION_ROOT',str(capture_root))
    owner=C.IDBackgroundCapture(engine,lambda event:None)
    def context():
        spec=C.Projection.from_pipeline(pipe)
        return {'document_id':str(engine._load_id),'recipe_document_id':'a'*32,
                'recipe_revision':str(engine.revision),'full_source':[8,6],
                'presentation_width':4,'presentation_height':3},spec
    monkeypatch.setattr(owner,'_context',context)
    reference_rgb=np.broadcast_to(np.array([.2,.4,.8],np.float32),(64,64,3)).copy()
    reference_bytes=b'fixture immutable selected rendered reference'
    asset_id=sha256(reference_bytes).hexdigest();asset_path=tmp_path/(asset_id+'.npz')
    asset_path.write_bytes(reference_bytes)
    selection={'sample_id':'selected-sample','source':deepcopy(REFERENCE_SOURCE),
               'render_sha256':'3'*64,'asset_id':asset_id}
    reference={key:selection[key] for key in ('source','render_sha256','asset_id')}
    row={'id':selection['sample_id'],'deleted_at':None,'reference':deepcopy(reference)}
    catalog={'samples':[row]}
    monkeypatch.setattr(LIB,'SampleLibrary',lambda:SimpleNamespace(store=SimpleNamespace(read=lambda:nullcontext(catalog))))
    monkeypatch.setattr(A,'cache_root',lambda:tmp_path)
    loads=[]
    def load(root,binding):
        assert binding==reference and binding['source']!=SOURCE
        loads.append(deepcopy(binding));return SimpleNamespace(rgb=reference_rgb)
    monkeypatch.setattr(A,'load',load)
    return SimpleNamespace(owner=owner,engine=engine,pipe=pipe,rgb=rgb,alpha=alpha,
        raster_calls=raster_calls,preview_calls=preview_calls,reference_rgb=reference_rgb,
        selection=selection,asset_path=asset_path,row=row,loads=loads,root=capture_root)


def arm(rig,mode):
    request={'cmd':'color_picker_capture','action':'arm','capture_id':'b'*32,'ticket':'1',
        'document_id':'7','epoch':'c'*32,'picker_action':ACTIONS[mode],'picker_channel':'master'}
    if mode=='reference':request['reference']=deepcopy(rig.selection)
    return rig.owner.handle(request)['descriptor']


def present(rig,descriptor):
    return rig.owner.handle({'cmd':'color_picker_capture','action':'presented',
        **{key:descriptor[key] for key in ('capture_id','ticket','document_id','generation')}})


def request(descriptor,**region):
    return {'cmd':'background','action':'id_sample','request_id':'owned-sample',
        **{key:deepcopy(descriptor[key]) for key in ('document_id',*C.PROOF_KEYS,'picker_mode','source_binding')},
        'region':region or {'x':1,'y':1,'width':1,'height':1}}


@pytest.mark.parametrize('mode',ACTIONS)
def test_three_modes_keep_private_capture_float_input_and_presented_lease(monkeypatch,tmp_path,mode):
    r=rig(monkeypatch,tmp_path);d=arm(r,mode)
    with pytest.raises(ValueError,match='presented'):r.owner.sample(request(d))
    packet=(r.owner.path/'capture.lrcp').read_bytes()
    assert packet[:4]==b'LRCP' and len(packet)==128+d['width']*d['height']*4
    assert r.owner.path.parent==r.root and r.owner.path.stat().st_mode&0o777==0o700
    assert d['source_binding']['target']['source']==SOURCE
    assert len(json.dumps(d['source_binding']))<4096
    assert present(r,d)['success']
    sampled=r.owner.sample(request(d))
    expected=r.reference_rgb[1,1] if mode=='reference' else r.rgb[1,1]
    assert sampled['rgb']==np.floor(expected.astype(np.float64)*255+.5).astype(np.uint8).tolist()
    assert sampled['sample_pixels']==1 and sampled['quality']=='proxy-float-input'
    actual=r.owner.capture['pixels'][0,:,1,1].cpu().numpy()
    np.testing.assert_array_equal(actual,expected)
    assert not np.array_equal(actual,r.pipe.repair_base[0,:,1,1].numpy())
    if mode=='reference':
        assert d['source_binding']['reference']['source']==REFERENCE_SOURCE
        assert d['full_source']==[64,64] and r.loads
    else:
        assert d['source_binding']['source']==SOURCE and d['full_source']==[8,6]
        assert not r.loads
    if mode=='subject':
        assert r.raster_calls and all(call[1] is None for call in r.raster_calls)
        np.testing.assert_array_equal(r.raster_calls[0][2],r.rgb)
    before=r.owner.path
    r.owner.handle({'cmd':'color_picker_capture','action':'cancel',
        **{key:d[key] for key in ('capture_id','ticket','document_id')}})
    assert r.owner.capture is None and not before.exists()


@pytest.mark.parametrize('mode',ACTIONS)
@pytest.mark.parametrize('boundary',['presented','sample'])
def test_actual_source_mutation_is_rejected_without_document_or_recipe_id_change(monkeypatch,tmp_path,mode,boundary):
    r=rig(monkeypatch,tmp_path);d=arm(r,mode)
    if boundary=='sample':present(r,d)
    r.pipe.src_f32[0,0,0,0]+=.01
    assert r.engine._load_id==7 and r.engine.revision==9
    with pytest.raises(ValueError):
        present(r,d) if boundary=='presented' else r.owner.sample(request(d))


@pytest.mark.parametrize('mode',ACTIONS)
@pytest.mark.parametrize('changed',['pixels','coverage','descriptor'])
@pytest.mark.parametrize('boundary',['presented','sample'])
def test_retained_capture_bytes_cannot_change_behind_same_lease(monkeypatch,tmp_path,mode,changed,boundary):
    r=rig(monkeypatch,tmp_path);d=arm(r,mode)
    if boundary=='sample':present(r,d)
    if changed=='descriptor':r.owner.capture['descriptor']['projection']['rotation']=1.
    else:r.owner.capture[changed][0,0,1,1]=.75
    with pytest.raises(ValueError):
        present(r,d) if boundary=='presented' else r.owner.sample(request(d))


def test_arm_response_does_not_alias_the_private_sealed_descriptor(monkeypatch,tmp_path):
    r=rig(monkeypatch,tmp_path);d=arm(r,'original')
    d['source_binding']['target']['source']['sha256']='f'*64
    assert r.owner.capture['descriptor']['source_binding']['target']['source']==SOURCE


@pytest.mark.parametrize('changed',['asset_bytes','catalog_render','deleted','selected_sample'])
@pytest.mark.parametrize('boundary',['presented','sample'])
def test_reference_selection_and_actual_asset_are_rechecked(monkeypatch,tmp_path,changed,boundary):
    r=rig(monkeypatch,tmp_path);d=arm(r,'reference')
    if boundary=='sample':present(r,d)
    if changed=='asset_bytes':r.asset_path.write_bytes(b'changed immutable asset bytes')
    elif changed=='catalog_render':r.row['reference']['render_sha256']='f'*64
    elif changed=='deleted':r.row['deleted_at']='2026-10-23T00:00:00Z'
    else:r.owner.reference_selection['sample_id']='another-sample'
    with pytest.raises(ValueError):
        present(r,d) if boundary=='presented' else r.owner.sample(request(d))


@pytest.mark.parametrize('changed',['review','projection','target_render'])
def test_reference_still_owns_current_target_review_and_projection(monkeypatch,tmp_path,changed):
    r=rig(monkeypatch,tmp_path);d=arm(r,'reference');present(r,d)
    if changed=='review':r.engine._id_background['edge']=1.
    elif changed=='projection':r.pipe.crop_rotation=90.
    else:r.engine.review_key='changed-current-render-proof'
    with pytest.raises(ValueError):r.owner.sample(request(d))


@pytest.mark.parametrize('boundary',['presented','sample'])
def test_contact_actual_coverage_change_is_rejected_with_same_review_digest(monkeypatch,tmp_path,boundary):
    r=rig(monkeypatch,tmp_path);d=arm(r,'subject')
    if boundary=='sample':present(r,d)
    before=r.engine._id_background['support']['contact']['recipe_sha256']
    r.alpha[1,1]=0.
    assert r.engine._id_background['support']['contact']['recipe_sha256']==before
    with pytest.raises(ValueError):
        present(r,d) if boundary=='presented' else r.owner.sample(request(d))


def test_contact_coverage_remains_conservative_and_dimming_is_not_sampled(monkeypatch,tmp_path):
    r=rig(monkeypatch,tmp_path);d=arm(r,'subject');present(r,d)
    result=r.owner.sample(request(d,x=1,y=1,width=2,height=1))
    assert result['sample_pixels']==1
    with pytest.raises(ValueError):r.owner.sample(request(d,x=2,y=1,width=1,height=1))
    packet=(r.owner.path/'capture.lrcp').read_bytes()
    display=np.frombuffer(packet[128:],np.uint8).reshape(3,4,4)
    assert np.all(display[1,2,:3]<display[1,1,:3])
    np.testing.assert_array_equal(r.owner.capture['pixels'][0,:,1,2].numpy(),r.rgb[1,2])


def test_subject_review_cannot_substitute_for_independent_contact_review(monkeypatch,tmp_path):
    r=rig(monkeypatch,tmp_path)
    r.engine._id_background['support']['subject']=reviewed('subject')
    r.engine._id_background['support']['contact']=None
    with pytest.raises(ValueError):arm(r,'subject')
    assert not r.raster_calls


@pytest.mark.parametrize('mode',ACTIONS)
@pytest.mark.parametrize('bad',[-.01,1.01,float('nan'),float('inf')])
def test_source_hdr_and_nonfinite_values_are_not_clipped(monkeypatch,tmp_path,mode,bad):
    r=rig(monkeypatch,tmp_path);r.pipe.src_f32[0,0,0,0]=bad
    with pytest.raises(ValueError):arm(r,mode)
    assert r.owner.capture is None


@pytest.mark.parametrize('bad',[-.01,1.01,float('nan'),float('inf')])
def test_reference_hdr_is_rejected_before_proxy_interpolation(monkeypatch,tmp_path,bad):
    r=rig(monkeypatch,tmp_path);r.reference_rgb[0,0,0]=bad
    with pytest.raises(ValueError):arm(r,'reference')
    assert r.owner.capture is None and r.loads


@pytest.mark.parametrize('dtype',[np.uint8,np.float64])
def test_picker_proof_never_casts_wrong_source_dtype_into_float_evidence(dtype):
    with pytest.raises(ValueError):C._array_proof(np.zeros((3,4,3),dtype),3)


@pytest.mark.parametrize('bad',[-.01,1.01,float('nan'),float('inf')])
def test_contact_raster_cannot_supply_clipped_or_invalid_coverage(monkeypatch,tmp_path,bad):
    r=rig(monkeypatch,tmp_path);r.alpha[0,0]=bad
    with pytest.raises(ValueError):arm(r,'subject')
    assert r.owner.capture is None


def test_contact_prompted_input_uses_canonical_source_not_original_or_proxy(monkeypatch,tmp_path):
    from lumaretouch_engine import creative_derived_prompted as Q
    from lumaretouch_engine import prompted_mask_resolver as P
    from lumaretouch_engine import prompted_mask_source as PS
    r=rig(monkeypatch,tmp_path)
    full=np.full((6,8,3),.375,np.float32);packet=Q.from_pixels(SOURCE,full)
    obj={'id':'prompted-contact','name':'Reviewed prompted contact','enabled':True,'operation':'add',
         'kind':'prompted','opacity':1.,'feather':0.,'selection':{
         'prompts':{'points':[{'x':.5,'y':.5,'label':1}],'box':None},'candidate':0,'device':'cpu',
         'input_sha256':packet['descriptor']['input_sha256'],
         'model':{'id':'fixture-sam','checkpoint_sha256':'4'*64,'config_sha256':'5'*64,
                  'code_revision':'6'*40,'contract':PS.CONTRACT}}}
    support=r.engine._id_background['support']['contact']
    support['mask']['recipe']['objects']=[obj];support['recipe_sha256']=U.digest(support['mask'])
    monkeypatch.setattr(Q,'capture',lambda engine:deepcopy(packet))
    dependency=['immutable-installed-model-v1',(1,2,3,4,5)]
    monkeypatch.setattr(P,'dependency_stamp',lambda:deepcopy(dependency))
    d=arm(r,'subject');present(r,d)
    called=r.raster_calls[0]
    assert called[1] is None and called[3]['source_input']==packet
    assert called[3]['source_input']['descriptor']['source']==SOURCE
    assert called[3]['source_input']['descriptor']['width']==8
    assert d['source_binding']['prompted_sha256'] is not None
    before=len(r.raster_calls)
    dependency[0]='changed-installed-model-v2'
    with pytest.raises(ValueError):r.owner.sample(request(d))
    assert len(r.raster_calls)==before  # stale model proof fails before replay/inference


def test_reference_cannot_be_supplied_to_another_picker_mode(monkeypatch,tmp_path):
    r=rig(monkeypatch,tmp_path)
    with pytest.raises(ValueError):
        r.owner.handle({'cmd':'color_picker_capture','action':'arm','capture_id':'b'*32,'ticket':'1',
            'document_id':'7','epoch':'c'*32,'picker_action':'id_background','picker_channel':'master',
            'reference':deepcopy(r.selection)})
