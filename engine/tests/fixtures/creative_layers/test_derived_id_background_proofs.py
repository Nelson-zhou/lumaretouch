"""AUTHORED / UNRUN: source-owned ID-background evidence and float fences.

These unit fixtures do not establish SAM quality, native mask replay, ICC asset
decoding, GPU alignment, encoder results, photographic acceptance or parity.
No test or import was executed while authoring this change.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_id_background as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_derived_repair_runtime as R
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_prompted as Q
from lumaretouch_engine import prompted_mask_resolver as P
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import id_background_state as S
from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import id_background_assets as A


SOURCE={'sha256':'1'*64,'width':8,'height':6}
STAMP=(1,2,3,4,5)
ASSET_BYTES=b'Frozen bundle identity only; no decoder is exercised by these tests.'
ASSET={'path':'/no-longer-present/background.tiff','sha256':sha256(ASSET_BYTES).hexdigest(),
    'width':12,'height':9,'bits':16,'working_color':'linear-srgb-f32',
    'icc_sha256':'4'*64,'pixels_sha256':'5'*64,'alpha_sha256':'6'*64}


def operand(kind='brush',ident='mark',enabled=True):
    obj={'id':ident,'name':ident,'enabled':enabled,'kind':kind,'operation':'add',
         'opacity':.8,'feather':.2}
    if kind=='brush':obj.update(axes=[[.08,0.],[0.,.08]],points=[[.5,.3]])
    elif kind=='color_range':obj.update(color=[.4,.5,.6],tolerance=.15,invert=False)
    elif kind=='luminance_range':obj.update(low=.2,high=.7)
    elif kind=='prompted':
        obj['selection']={'prompts':{'points':[{'x':.4,'y':.5,'label':1}],'box':None},
            'candidate':0,'device':'cpu','input_sha256':'7'*64,
            'model':{'id':'unit-sam','checkpoint_sha256':'8'*64,'config_sha256':'9'*64,
                     'code_revision':'a'*40,'contract':'unit-owned-input-v1'}}
    return obj


def support(category,objects=None,source=None):
    mask={'recipe':{'version':1,'domain':'source-normalized',
                   'objects':objects if objects is not None else [operand(ident=category)]},
          'source':deepcopy(SOURCE if source is None else source),'semantic_owner':None}
    return {'version':1,'category':category,'reviewed':True,'mask':mask,'recipe_sha256':U.digest(mask)}


def recipe(*,active=False,all_supports=False,asset=False,prompted=False):
    value=S.empty();value['source']=deepcopy(SOURCE);value['enabled']=active
    value['support']['subject']=support('subject',[operand('prompted' if prompted else 'brush')])
    if all_supports:
        value['support']['contact']=support('contact',[operand('color_range','contact')])
        value['support']['all']=support('all',[operand('luminance_range','all',False)])
    if asset:value['background'].update(kind='asset',asset=deepcopy(ASSET))
    return value


def bundle():
    return {'binding':deepcopy(ASSET),'content':[ASSET_BYTES]}


def context(value=None):
    value=recipe() if value is None else value
    return {'version':1,'source':deepcopy(SOURCE),'original_sha256':'2'*64,
        'recipe':deepcopy(value),'recipe_sha256':C.recipe_digest(value),
        'asset_identity':{'binding':deepcopy(ASSET),'byte_count':len(ASSET_BYTES)}
            if value['background']['asset'] is not None else None}


def bind_source(monkeypatch):
    rgba=np.full((6,8,4),.25,dtype='<f4');rgba[:,:,3]=1.
    record={'width':8,'height':6,'content':rgba.tobytes()}
    monkeypatch.setattr(D,'record',lambda owner:record)
    monkeypatch.setattr(D,'binding',lambda owner:deepcopy(SOURCE))
    return record


def provenance(monkeypatch):
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    monkeypatch.setattr(M,'source_digest',lambda path:'2'*64)


def test_all_independent_reviews_remain_source_owned_when_disabled(monkeypatch):
    bind_source(monkeypatch);value=recipe(all_supports=True)
    assert C.validate_state({'creative_base':object(),'id_background':value})==value
    for category in S.CATEGORIES:
        bad=deepcopy(value);mask=bad['support'][category]['mask']
        mask['source']['sha256']='2'*64
        bad['support'][category]['recipe_sha256']=U.digest(mask)
        with pytest.raises(ValueError):C.validate(bad,SOURCE)
    # A coherently rebound whole recipe still cannot claim the physical file.
    bad=deepcopy(value);bad['source']['sha256']='2'*64
    for binding in bad['support'].values():
        binding['mask']['source']=deepcopy(bad['source'])
        binding['recipe_sha256']=U.digest(binding['mask'])
    with pytest.raises(ValueError,match='another effective source'):C.validate(bad,SOURCE)


def test_manual_colour_and_luminance_are_retained_not_semantic_shortcuts():
    value=recipe(all_supports=True)
    assert C.validate(value,SOURCE)==value
    assert value['support']['all']['mask']['recipe']['objects'][0]['enabled'] is False
    for kind in ('semantic','full'):
        obj=operand();obj.pop('axes');obj.pop('points');obj['kind']=kind
        if kind=='semantic':obj['channel']='person'
        else:obj.update(opacity=1.,feather=0.)
        bad=recipe();bad['support']['subject']=support('subject',[obj])
        with pytest.raises(ValueError):C.validate(bad,SOURCE)


def test_aliases_cannot_hide_retained_review_or_bundle(monkeypatch):
    bind_source(monkeypatch)
    for value in (
        {'creative_base':object(),'_creative_base':None,'id_background':S.empty()},
        {'creative_base':object(),'id_background':S.empty(),'_id_background':recipe()},
        {'creative_base':object(),'id_background_bundle':None,'_id_background_bundle':bundle()},
    ):
        with pytest.raises(ValueError):C.validate_state(value)


def test_disabled_prompted_history_capture_needs_no_model_or_canonical_decode(monkeypatch):
    bind_source(monkeypatch);provenance(monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Disabled retained intent must remain editable')
    monkeypatch.setattr(P,'dependency_stamp',forbidden)
    monkeypatch.setattr(P,'fields',forbidden)
    monkeypatch.setattr(Q,'capture',forbidden)
    value=recipe(prompted=True,all_supports=True)
    frozen=C.capture({'creative_base':object(),'id_background':value},path='physical-original')
    assert frozen['recipe']==value and frozen['source']==SOURCE
    assert set(frozen)=={'version','source','original_sha256','recipe','recipe_sha256','asset_identity'}
    assert C.verify_context(frozen,SOURCE,value) is frozen


def test_asset_identity_comes_from_frozen_bundle_not_external_link(monkeypatch):
    bind_source(monkeypatch);provenance(monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Frozen asset must not depend on linked file or decode')
    monkeypatch.setattr(A,'verify',forbidden);monkeypatch.setattr(A,'read',forbidden)
    monkeypatch.setattr(A,'unpack',forbidden)
    for active in (False,True):
        value=recipe(active=active,asset=True)
        state={'creative_base':object(),'id_background':value,'id_background_bundle':bundle()}
        frozen=C.capture(state,path='physical-original')
        assert frozen['asset_identity']['binding']==ASSET
        assert C.verify_context(frozen,SOURCE,value,bundle=bundle()) is frozen
        broken=bundle();broken['content']=[ASSET_BYTES+b'changed']
        with pytest.raises(ValueError):C.verify_context(frozen,SOURCE,value,bundle=broken)
        with pytest.raises(ValueError):C.verify_context(frozen,SOURCE,value,bundle=None)
        state['id_background_bundle']=None
        with pytest.raises(ValueError):C.capture(state,path='physical-original')


def test_frozen_context_retains_exact_review_category_recipe_asset_and_provenance():
    frozen=context(recipe(asset=True,all_supports=True))
    assert C.verify_context(frozen,SOURCE,bundle=bundle()) is frozen
    changes=(
        lambda c:c['recipe'].__setitem__('selected_support','contact'),
        lambda c:c['recipe']['support']['all']['mask']['recipe']['objects'][0].__setitem__('enabled',True),
        lambda c:c['recipe']['background']['asset'].__setitem__('bits',8),
        lambda c:c['recipe']['shadow'].__setitem__('opacity',.8),
        lambda c:c['asset_identity']['binding'].__setitem__('icc_sha256','b'*64),
        lambda c:c['asset_identity'].__setitem__('byte_count',True),
        lambda c:c.__setitem__('original_sha256','invalid'),
        lambda c:c.__setitem__('version',True),
        lambda c:c.__setitem__('prompted_input',{'pixels':b'hidden'}),
    )
    for change in changes:
        bad=deepcopy(frozen);change(bad)
        with pytest.raises(ValueError):C.verify_context(bad,SOURCE,bundle=bundle())


def test_snapshot_requires_all_retained_evidence_and_exact_source_grid(monkeypatch):
    bind_source(monkeypatch);value=recipe(all_supports=True);frozen=context(value)
    snap={'creative_base':object(),'id_background':value,'creative_id_background_context':frozen}
    assert C.verify_snapshot(snap,shape=(6,8)) is frozen
    with pytest.raises(ValueError):C.verify_snapshot(snap,shape=(3,4))
    missing={k:v for k,v in snap.items() if k!='creative_id_background_context'}
    with pytest.raises(ValueError):C.verify_snapshot(missing)
    snap['id_background']=deepcopy(value);snap['id_background']['edge']=2.
    with pytest.raises(ValueError):C.verify_snapshot(snap)
    assert C.capture({'creative_base':object(),'id_background':S.empty()}) is None
    assert C.verify_snapshot({'creative_base':object(),'id_background':S.empty()}) is None
    with pytest.raises(ValueError):C.verify_snapshot({**snap,'id_background':S.empty()})
    monkeypatch.setattr(D,'record',lambda owner:None)
    with pytest.raises(ValueError):C.verify_snapshot(snap)


def test_original_provenance_is_separate_and_capture_races_are_rejected(monkeypatch):
    bind_source(monkeypatch);provenance(monkeypatch);frozen=context()
    assert C.verify_context(frozen,SOURCE,path='physical-original') is frozen
    monkeypatch.setattr(M,'source_digest',lambda path:SOURCE['sha256'])
    with pytest.raises(ValueError):C.verify_context(frozen,SOURCE,path='physical-original')
    monkeypatch.setattr(M,'source_digest',lambda path:'2'*64)
    stamps=iter([STAMP,(1,2,3,4,6)])
    monkeypatch.setattr(M,'file_stamp',lambda path:next(stamps))
    with pytest.raises(ValueError):C.capture({'creative_base':object(),'id_background':recipe()},path='physical-original')


class Tensor:
    """Only the read-only adapter used for actual source/repair evidence."""
    def __init__(self,array):self.array=array
    def __getitem__(self,index):return Tensor(self.array[index])
    def permute(self,*axes):return Tensor(self.array.transpose(axes))
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.array


def live(monkeypatch,*,active=True,prompted=False):
    bind_source(monkeypatch);provenance(monkeypatch)
    proxy=np.full((3,4,3),102,np.uint8);pixels=proxy.astype(np.float32)/255.
    tensor=lambda rgb:Tensor(rgb.transpose(2,0,1)[None].copy())
    pipe=SimpleNamespace(h=3,w=4,src_f32=tensor(pixels),repair_base=tensor(pixels+.1),
        repair_ops=[],redo_ops=[],_creative_repair_source=deepcopy(SOURCE),has_background=lambda:False,
        deform_version=0,deform_amounts={'slim_face':0.},high_precision_warp=False,people_prepared=None)
    stack=REPAIRS.digest_ops([],[],SOURCE)
    pipe._creative_repair_evidence=R.make_evidence(SOURCE,pixels,pixels+.1,stack)
    pipe._creative_repair_input=deepcopy(pipe._creative_repair_evidence['input'])
    engine=SimpleNamespace(_vram=pipe,_doc_path='physical-original',
        _docs=[{'path':'physical-original','_local_source_stamp':STAMP}],_doc_index=0,
        _id_background=recipe(active=active,prompted=prompted,all_supports=True),
        _id_background_bundle=None,_repair_ops=[],_redo_ops=[],_bg={'active':False})
    monkeypatch.setattr(D,'analysis_rgb',lambda owner:proxy)
    return engine,proxy,pixels


def test_preview_proves_actual_pre_repair_pixels_and_all_retained_reviews(monkeypatch):
    engine,_,pixels=live(monkeypatch)
    frozen,actual,key=C.preview(engine)
    np.testing.assert_array_equal(actual,pixels)
    assert not np.array_equal(actual,engine._vram.repair_base[0].permute(1,2,0).numpy())
    assert frozen['source']==SOURCE and frozen['original_sha256']!=SOURCE['sha256']
    assert C.key(engine,engine._id_background)==key
    engine._id_background['selected_support']='contact'
    assert C.key(engine,engine._id_background)!=key
    neutral,actual,_=C.preview(engine,S.empty())
    assert neutral is None
    np.testing.assert_array_equal(actual,pixels)


@pytest.mark.parametrize('target',['input','output','analysis','stack','original','source'])
def test_preview_rejects_actual_input_output_history_and_provenance_changes(monkeypatch,target):
    engine,proxy,_=live(monkeypatch)
    if target=='input':engine._vram.src_f32.array[0,0,0,0]+=.01
    elif target=='output':engine._vram.repair_base.array[0,0,0,0]+=.01
    elif target=='analysis':proxy[0,0,0]+=1
    elif target=='stack':monkeypatch.setattr(REPAIRS,'stack_digest',lambda owner:'b'*64)
    elif target=='original':engine._docs[0]['_local_source_stamp']=(1,2,3,4,6)
    else:engine._vram._creative_repair_source={**SOURCE,'sha256':'b'*64}
    with pytest.raises(ValueError):C.preview(engine)


def test_preview_key_covers_live_deformation_all_person_geometry_and_activation(monkeypatch):
    engine,_,_=live(monkeypatch,active=False);pipe=engine._vram
    key=C.key(engine,engine._id_background)
    pipe.deform_amounts['slim_face']=.5
    changed=C.key(engine,engine._id_background);assert changed!=key
    pipe.deform_version+=1;pipe.high_precision_warp=True
    assert C.key(engine,engine._id_background)!=changed
    delta=np.zeros((1,3,4,2),np.float32)
    pipe.people_prepared=SimpleNamespace(geometry=SimpleNamespace(delta=delta))
    pipe.people_key=('source','people-revision');pipe.people_origin=(0,0)
    key=C.key(engine,engine._id_background);delta[0,1,1,0]=.1
    assert C.key(engine,engine._id_background)!=key
    key=C.key(engine,engine._id_background);engine._bg['active']=True
    assert C.key(engine,engine._id_background)!=key
    engine._id_background['enabled']=True
    with pytest.raises(ValueError,match='overwrite'):C.preview(engine)
    engine._id_background['enabled']=False;delta[0,1,1,0]=np.nan
    with pytest.raises(ValueError):C.preview(engine)


def test_active_prompted_key_owns_canonical_packet_and_current_dependency(monkeypatch):
    engine,_,_=live(monkeypatch,prompted=True)
    packet={'descriptor':{'input_sha256':'7'*64}}
    monkeypatch.setattr(Q,'capture',lambda owner:packet)
    monkeypatch.setattr(Q,'cache_identity',lambda raw,source:('canonical-model-input',source['sha256']))
    monkeypatch.setattr(P,'dependency_stamp',lambda:('installed-v1',STAMP))
    key=C.key(engine,engine._id_background)
    monkeypatch.setattr(P,'dependency_stamp',lambda:('installed-v2',STAMP))
    assert C.key(engine,engine._id_background)!=key
    packet['descriptor']['input_sha256']='b'*64
    with pytest.raises(ValueError,match='another immutable model input'):C.preview(engine)
    engine._id_background['enabled']=False
    def missing():raise AssertionError('Disabled recipe must not load a model')
    monkeypatch.setattr(P,'dependency_stamp',missing)
    assert C.preview(engine)[0]['recipe']['enabled'] is False


@pytest.mark.parametrize('channel,bad',[(3,.5),(0,-.01),(0,1.01),(0,np.nan)])
def test_proxy_cannot_hide_canonical_alpha_hdr_or_nonfinite_source(monkeypatch,channel,bad):
    engine,_,_=live(monkeypatch,active=False)
    rgba=np.full((6,8,4),.25,dtype='<f4');rgba[:,:,3]=1.;rgba[0,0,channel]=bad
    monkeypatch.setattr(D,'record',lambda owner:{'content':rgba.tobytes(),'width':8,'height':6})
    with pytest.raises(ValueError,match='opaque SDR'):C.preview(engine,S.empty())


def test_real_content_addressed_source_mutation_is_not_blessed():
    from lumaretouch_engine.creative_document_assets import make_asset
    rgba=np.full((6,8,4),.25,dtype='<f4');rgba[:,:,3]=1.
    asset=make_asset('rgba',8,6,rgba.tobytes());owner={'creative_base':asset}
    C._supported_source(owner)
    rgba[0,0,0]=.3;owner['creative_base']={**asset,'content':rgba.tobytes()}
    with pytest.raises(ValueError,match='content digest'):C._supported_source(owner)


def test_export_requires_canonical_full_float_before_prepare_not_proxy_or_quantization(monkeypatch):
    bind_source(monkeypatch);frozen=context(recipe(all_supports=True))
    spec=SimpleNamespace(creative_base=object(),id_background=frozen['recipe'],
        creative_id_background_context=frozen,id_background_bundle=None)
    pixels=np.full((6,8,3),.400001,np.float32)
    with pytest.raises(ValueError):C.verify_export(spec,pixels)
    C.stamp_pixels(spec,pixels)
    assert C.verify_export(spec,pixels) is frozen
    for bad in (pixels+.1,pixels[:3,:4],np.round(pixels*255).astype(np.uint8),
                np.round(pixels*65535).astype(np.uint16),pixels.astype(np.float64),
                np.concatenate((pixels,np.ones((6,8,1),np.float32)),axis=2)):
        with pytest.raises(ValueError):C.verify_export(spec,bad)
    for divisor in (255.,65535.,True):
        with pytest.raises(ValueError):C.verify_export(spec,pixels,divisor)
    spec.id_background=deepcopy(frozen['recipe']);spec.id_background['edge']=2.
    with pytest.raises(ValueError):C.verify_export(spec,pixels)


def test_export_rechecks_full_frozen_asset_bundle_after_canonical_resolution(monkeypatch):
    bind_source(monkeypatch);frozen=context(recipe(asset=True))
    spec=SimpleNamespace(creative_base=object(),id_background=frozen['recipe'],
        creative_id_background_context=frozen,id_background_bundle=bundle())
    pixels=np.full((6,8,3),.4,np.float32);C.stamp_pixels(spec,pixels)
    spec.id_background_bundle['content']=[b'not the frozen asset']
    with pytest.raises(ValueError):C.verify_export(spec,pixels)


@pytest.mark.parametrize('bad',[np.nan,np.inf,-.01,1.01])
def test_export_refuses_nonfinite_or_hdr_without_clipping(monkeypatch,bad):
    bind_source(monkeypatch);frozen=context()
    spec=SimpleNamespace(creative_base=object(),id_background=frozen['recipe'],
        creative_id_background_context=frozen,id_background_bundle=None)
    pixels=np.full((6,8,3),.4,np.float32);pixels[0,0,0]=bad
    with pytest.raises(ValueError):C.stamp_pixels(spec,pixels)
