"""AUTHORED / UNRUN: immutable sky intent, locator and canonical-float fences.

These unit cases do not establish decoder/ICC quality, semantic inference, Rust
mask replay, GPU alignment, full export codecs or photographic acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_sky as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_derived_repair_runtime as R
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import sky_replacement_state as S
from lumaretouch_engine import sky_replacement_assets as A


SOURCE={'sha256':'1'*64,'width':8,'height':6}
STAMP=(1,2,3,4,5)
ASSET_STAMP=(6,7,8,9,10)
ASSET={'path':'/linked/sky.tiff','sha256':'3'*64,'width':12,'height':9,
       'bits':16,'working_color':'encoded-srgb','icc_sha256':'4'*64}


def brush(ident):
    return {'id':ident,'name':ident,'enabled':True,'kind':'brush','operation':'add',
        'opacity':.8,'feather':.2,'axes':[[.08,0.],[0.,.08]],'points':[[.5,.3]]}


def recipe(*,active=False,all_regions=False):
    value=S.empty();value['enabled']=active;value['source']=deepcopy(SOURCE)
    value['asset']=deepcopy(ASSET);value['person_mode']='none'
    value['regions']['sky']['objects']=[brush('sky-stroke')]
    if all_regions:
        value['person_mode']='marked'
        value['regions']['person']['objects']=[brush('person-stroke')]
        value['regions']['water']['objects']=[brush('water-stroke')]
        value['recovery']['objects']=[brush('recovery-stroke')]
        value['horizon']=.5
    return value


def context(*,active=False,all_regions=False):
    value=recipe(active=active,all_regions=all_regions)
    return {'version':1,'source':deepcopy(SOURCE),'original_sha256':'2'*64,
        'recipe':value,'recipe_sha256':C.recipe_digest(value),
        'asset_stamp':ASSET_STAMP if active else None}


def bind_source(monkeypatch):
    monkeypatch.setattr(D,'record',lambda owner:object())
    monkeypatch.setattr(D,'binding',lambda owner:deepcopy(SOURCE))


def provenance(monkeypatch):
    monkeypatch.setattr(M,'file_stamp',lambda path:ASSET_STAMP if path==ASSET['path'] else STAMP)
    monkeypatch.setattr(M,'source_digest',lambda path:'3'*64 if path==ASSET['path'] else '2'*64)
    monkeypatch.setattr(A,'verify',lambda value:ASSET_STAMP)


def test_disabled_all_regions_and_recovery_still_own_the_effective_source(monkeypatch):
    bind_source(monkeypatch)
    value=recipe(all_regions=True)
    assert C.validate_state({'creative_base':object(),'sky_replacement':value})==value
    assert all(value['regions'][region]['objects'] for region in S.REGIONS)
    assert value['recovery']['objects']
    value['source']['sha256']='5'*64
    with pytest.raises(ValueError,match='another effective source'):C.validate(value,SOURCE)
    value=recipe();value['source']['width']+=1
    with pytest.raises(ValueError):C.validate(value,SOURCE)


def test_disabled_asset_only_and_parameters_are_retained_without_opening_link(monkeypatch):
    bind_source(monkeypatch);provenance(monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Disabled links must remain editable without decoding')
    monkeypatch.setattr(A,'verify',forbidden)
    monkeypatch.setattr(A,'read',forbidden)
    for bits in (8,16):
        value=S.empty();value['asset']={**ASSET,'bits':bits}
        selected=deepcopy(value['asset'])
        value['parameters']['temperature']=12.
        frozen=C.capture({'creative_base':object(),'sky_replacement':value},path='physical-original')
        assert frozen['source']==SOURCE and frozen['recipe']['source'] is None
        assert frozen['recipe']['asset']==selected and frozen['asset_stamp'] is None
        assert C.verify_context(frozen,SOURCE,value) is frozen
        value['asset']['path']='/different/sky.tiff'
        with pytest.raises(ValueError):C.verify_context(frozen,SOURCE,value)
    value=S.empty();value['parameters']['temperature']=12.
    frozen=C.capture({'creative_base':object(),'sky_replacement':value},path='physical-original')
    assert frozen['recipe']==value and frozen['recipe']['asset'] is None


def test_invalid_disabled_asset_depth_icc_and_path_are_not_dropped():
    for field,bad in (('bits',32),('working_color','linear-rgb'),('path','relative.tiff'),
                      ('icc_sha256','not-a-digest'),('sha256','5'*63),('width',True)):
        value=recipe();value['asset'][field]=bad
        with pytest.raises(ValueError):C.validate(value,SOURCE)


def test_ambiguous_aliases_cannot_hide_disabled_or_foreign_intent(monkeypatch):
    bind_source(monkeypatch)
    for value in (
        {'creative_base':object(),'sky_replacement':S.empty(),'_sky_replacement':recipe()},
        {'creative_base':object(),'_creative_base':None,'sky_replacement':S.empty()},
    ):
        with pytest.raises(ValueError):C.validate_state(value)


def automatic():
    from lumaretouch_engine.sky_semantic import manifest
    return {'version':1,'domain':'source-normalized','source':deepcopy(SOURCE),
        'model':manifest.identity(),'host':{key:'test' for key in ('python','torch','torchvision','numpy','Pillow')},
        'device':'cpu','input_sha256':'6'*64,'input_size':[4,3],
        'fields_sha256':{key:'7'*64 for key in S.REGIONS},'regions':{'sky':.5}}


@pytest.mark.parametrize('active',[False,True])
def test_automatic_proposals_never_rebind_to_the_physical_original(monkeypatch,active):
    bind_source(monkeypatch)
    value=recipe(active=active);value['semantic']=automatic()
    assert C.validate(value,SOURCE)==value
    assert C.validate_state({'creative_base':object(),'sky_replacement':value})==value
    wrong=deepcopy(value);wrong['semantic']['source']['sha256']='2'*64
    with pytest.raises(ValueError):C.validate(wrong,SOURCE)
    assert value['semantic'] is not None
    # An ordinary original photo retains its existing semantic contract.
    monkeypatch.setattr(D,'record',lambda owner:None)
    assert C.validate_state({'sky_replacement':value})==value


def test_exact_recipe_preserves_depth_icc_region_recovery_and_horizon():
    value=context(all_regions=True)
    assert C.verify_context(value,SOURCE) is value
    changes=(
        lambda c:c['recipe']['regions']['sky']['objects'][0]['points'][0].__setitem__(0,.6),
        lambda c:c['recipe']['recovery']['objects'][0].__setitem__('enabled',False),
        lambda c:c['recipe'].__setitem__('horizon',.6),
        lambda c:c['recipe']['asset'].__setitem__('bits',8),
        lambda c:c['recipe']['asset'].__setitem__('icc_sha256','5'*64),
        lambda c:c['recipe']['asset'].__setitem__('path','/different/sky.tiff'),
        lambda c:c.__setitem__('original_sha256','bad'),
        lambda c:c.__setitem__('version',True),
        lambda c:c.__setitem__('mask',np.zeros((3,4),np.float32)),
    )
    for change in changes:
        bad=deepcopy(value);change(bad)
        with pytest.raises(ValueError):C.verify_context(bad,SOURCE)
    with pytest.raises(ValueError):C.verify_context(value,{**SOURCE,'sha256':'5'*64})


def test_active_asset_stamp_is_verified_and_disabled_stamp_is_rejected(monkeypatch):
    provenance(monkeypatch);value=context(active=True)
    assert C.verify_context(value,SOURCE) is value
    monkeypatch.setattr(A,'verify',lambda asset:(6,7,8,9,11))
    with pytest.raises(ValueError,match='linked asset changed'):C.verify_context(value,SOURCE)
    for stamp in (list(ASSET_STAMP),(True,7,8,9,10),None):
        bad=deepcopy(value);bad['asset_stamp']=stamp
        with pytest.raises(ValueError):C.verify_context(bad,SOURCE)
    bad=context();bad['asset_stamp']=ASSET_STAMP
    with pytest.raises(ValueError):C.verify_context(bad,SOURCE)


def test_snapshot_requires_retained_evidence_and_complete_source_extent(monkeypatch):
    bind_source(monkeypatch);value=context(all_regions=True)
    snap={'creative_base':object(),'sky_replacement':value['recipe'],'creative_sky_context':value}
    assert C.verify_snapshot(snap,shape=(6,8)) is value
    with pytest.raises(ValueError):C.verify_snapshot(snap,shape=(3,4))
    snap['sky_replacement']=deepcopy(value['recipe']);snap['sky_replacement']['parameters']['blur']=2.
    with pytest.raises(ValueError):C.verify_snapshot(snap)
    with pytest.raises(ValueError):C.verify_snapshot({'creative_base':object(),'sky_replacement':recipe()})
    selected=S.empty();selected['asset']=deepcopy(ASSET)
    with pytest.raises(ValueError):C.verify_snapshot({'creative_base':object(),'sky_replacement':selected})


def test_neutral_recipe_needs_no_context_and_rejects_hidden_evidence(monkeypatch):
    bind_source(monkeypatch)
    assert C.capture({'creative_base':object(),'sky_replacement':S.empty()}) is None
    assert C.verify_snapshot({'creative_base':object(),'sky_replacement':S.empty()}) is None
    with pytest.raises(ValueError):
        C.verify_snapshot({'creative_base':object(),'sky_replacement':S.empty(),'creative_sky_context':context()})
    monkeypatch.setattr(D,'record',lambda owner:None)
    with pytest.raises(ValueError):C.verify_snapshot({'sky_replacement':recipe(),'creative_sky_context':context()})


def test_physical_original_provenance_is_separate_and_checked_for_races(monkeypatch):
    provenance(monkeypatch);value=context()
    assert C.verify_context(value,SOURCE,path='physical-original') is value
    monkeypatch.setattr(M,'source_digest',lambda path:SOURCE['sha256'])
    with pytest.raises(ValueError):C.verify_context(value,SOURCE,path='physical-original')
    monkeypatch.setattr(M,'source_digest',lambda path:'2'*64)
    stamps=iter([STAMP,(1,2,3,4,6)])
    monkeypatch.setattr(M,'file_stamp',lambda path:next(stamps))
    with pytest.raises(ValueError):C.verify_context(value,SOURCE,path='physical-original')


class Tensor:
    """Only the read-only adapter used by source/repair proof verification."""
    def __init__(self,array):self.array=array
    def __getitem__(self,index):return Tensor(self.array[index])
    def permute(self,*axes):return Tensor(self.array.transpose(axes))
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.array


def live(monkeypatch,*,active=True,repaired=True):
    bind_source(monkeypatch);provenance(monkeypatch)
    proxy=np.full((3,4,3),102,np.uint8);pixels=proxy.astype(np.float32)/255.
    tensor=lambda rgb:Tensor(rgb.transpose(2,0,1)[None].copy())
    pipe=SimpleNamespace(h=3,w=4,src_f32=tensor(pixels),repair_base=tensor(pixels+.1) if repaired else None,
        repair_ops=[],redo_ops=[],_creative_repair_source=deepcopy(SOURCE),has_background=lambda:False,
        deform_version=0,deform_amounts={'slim_face':0.},high_precision_warp=False,people_prepared=None)
    stack=REPAIRS.digest_ops([],[],SOURCE)
    pipe._creative_repair_evidence=R.make_evidence(SOURCE,pixels,pixels+.1 if repaired else None,stack)
    pipe._creative_repair_input=deepcopy(pipe._creative_repair_evidence['input'])
    engine=SimpleNamespace(_vram=pipe,_doc_path='physical-original',
        _docs=[{'path':'physical-original','_local_source_stamp':STAMP}],_doc_index=0,
        _sky_replacement=recipe(active=active),_repair_ops=[],_redo_ops=[])
    monkeypatch.setattr(D,'analysis_rgb',lambda owner:proxy)
    return engine,proxy,pixels


def test_preview_proves_actual_locator_not_repaired_pixels_or_file_identity(monkeypatch):
    engine,_,pixels=live(monkeypatch)
    frozen,actual,key=C.preview(engine)
    np.testing.assert_array_equal(actual,pixels)
    assert not np.array_equal(actual,engine._vram.repair_base[0].permute(1,2,0).numpy())
    assert frozen['source']==SOURCE and frozen['original_sha256']!=SOURCE['sha256']
    assert C.key(engine,engine._sky_replacement)==key
    neutral,locator,neutral_key=C.preview(engine,S.empty())
    assert neutral is None and neutral_key!=key
    np.testing.assert_array_equal(locator,pixels)


def test_preview_rejects_actual_source_repair_analysis_and_history_changes(monkeypatch):
    for target in ('input','output','analysis','stack','original','source'):
        engine,proxy,_=live(monkeypatch)
        if target=='input':engine._vram.src_f32.array[0,0,0,0]+=.01
        elif target=='output':engine._vram.repair_base.array[0,0,0,0]+=.01
        elif target=='analysis':proxy[0,0,0]+=1
        elif target=='stack':monkeypatch.setattr(REPAIRS,'stack_digest',lambda owner:'8'*64)
        elif target=='original':engine._docs[0]['_local_source_stamp']=(1,2,3,4,6)
        else:engine._vram._creative_repair_source={**SOURCE,'sha256':'9'*64}
        with pytest.raises(ValueError):C.preview(engine)
        monkeypatch.undo()


def test_preview_key_tracks_real_alignment_owner_and_all_person_field(monkeypatch):
    engine,_,_=live(monkeypatch);pipe=engine._vram
    key=C.key(engine,engine._sky_replacement)
    pipe.deform_amounts['slim_face']=.5
    changed=C.key(engine,engine._sky_replacement);assert changed!=key
    pipe.deform_version+=1
    changed_again=C.key(engine,engine._sky_replacement);assert changed_again!=changed
    pipe.high_precision_warp=True
    assert C.key(engine,engine._sky_replacement)!=changed_again
    delta=np.zeros((1,3,4,2),np.float32)
    pipe.people_prepared=SimpleNamespace(geometry=SimpleNamespace(delta=delta))
    pipe.people_key=('source','current-people-revision');pipe.people_origin=(0,0)
    people=C.key(engine,engine._sky_replacement)
    delta[0,1,1,0]=.1
    assert C.key(engine,engine._sky_replacement)!=people
    delta[0,1,1,0]=np.nan
    with pytest.raises(ValueError):C.preview(engine)


def test_neutral_locator_and_disabled_intent_remain_available_for_broken_link(monkeypatch):
    engine,_,_=live(monkeypatch)
    def missing(asset):raise ValueError('linked sky asset is missing')
    monkeypatch.setattr(A,'verify',missing)
    with pytest.raises(ValueError):C.preview(engine)
    assert C.preview(engine,S.empty())[0] is None
    value=deepcopy(engine._sky_replacement);value['enabled']=False
    frozen,_,_=C.preview(engine,value)
    assert frozen['recipe']['asset']==ASSET and frozen['asset_stamp'] is None
    assert engine._sky_replacement['enabled'] is True


def test_active_background_conflict_never_overwrites_sky(monkeypatch):
    engine,_,_=live(monkeypatch);engine._vram.has_background=lambda:True
    with pytest.raises(ValueError,match='overwrite sky'):C.preview(engine)
    value=deepcopy(engine._sky_replacement);value['enabled']=False
    assert C.preview(engine,value)[0]['recipe']==value


def test_export_requires_canonical_full_float_not_proxy_repair_or_quantization(monkeypatch):
    bind_source(monkeypatch);value=context()
    spec=SimpleNamespace(creative_base=object(),creative_sky_context=value,sky_replacement=value['recipe'])
    pixels=np.full((6,8,3),.400001,np.float32)
    with pytest.raises(ValueError):C.verify_export(spec,pixels)
    C.stamp_pixels(spec,pixels)
    assert C.verify_export(spec,pixels) is value
    for bad in (pixels+.1,pixels[:3,:4],np.round(pixels*255).astype(np.uint8),
                np.round(pixels*65535).astype(np.uint16),pixels.astype(np.float64)):
        with pytest.raises(ValueError):C.verify_export(spec,bad)
    for divisor in (255.,65535.,True):
        with pytest.raises(ValueError):C.verify_export(spec,pixels,divisor)
    spec.sky_replacement=deepcopy(value['recipe']);spec.sky_replacement['parameters']['brightness']=10.
    with pytest.raises(ValueError):C.verify_export(spec,pixels)


def test_export_asset_change_after_canonical_resolution_is_not_accepted(monkeypatch):
    bind_source(monkeypatch);provenance(monkeypatch);value=context(active=True)
    spec=SimpleNamespace(creative_base=object(),creative_sky_context=value,sky_replacement=value['recipe'])
    pixels=np.full((6,8,3),.4,np.float32);C.stamp_pixels(spec,pixels)
    monkeypatch.setattr(A,'verify',lambda asset:(6,7,8,9,11))
    with pytest.raises(ValueError):C.verify_export(spec,pixels)


@pytest.mark.parametrize('bad',[np.nan,np.inf,-.01,1.01])
def test_export_refuses_nonfinite_or_hdr_instead_of_clipping(monkeypatch,bad):
    bind_source(monkeypatch);value=context()
    spec=SimpleNamespace(creative_base=object(),creative_sky_context=value,sky_replacement=value['recipe'])
    pixels=np.full((6,8,3),.4,np.float32);pixels[0,0,0]=bad
    with pytest.raises(ValueError):C.stamp_pixels(spec,pixels)
